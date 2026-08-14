"""
DiagnosticLoop - bounded iterative reasoning loop for incident diagnosis.

Pattern: hypothesis -> evidence -> evaluate -> replan (bounded)

The LLM acts as the reasoning brain:
1. Generate initial hypotheses from the alert
2. LOOP (bounded by max_iterations and confidence_threshold):
   a. Plan which evidence to collect to confirm/reject current hypotheses
   b. Collect evidence via an EvidenceProvider (diagnostic agents)
   c. Evaluate: update hypothesis confidences based on new evidence
   d. If a hypothesis reaches confidence_threshold -> conclude (root cause found)
   e. Otherwise replan: refine/add/drop hypotheses and iterate
3. Emit final RCA with full iteration trace (auditable)
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

AVAILABLE_AGENTS_DESC = """Available diagnostic agents (READ-ONLY) and their checks:
1. "grafana"       - Metrics & Dashboards (cpu_usage, memory_usage, disk_io, network, gc_activity, latency_p99, throughput)
2. "kibana"        - Logs & Search (error_logs, container_logs, db_timeout_logs, oom_events, exception_traces)
3. "opentelemetry" - Traces & Spans (slowest_spans, latency_breakdown, dependency_calls, error_rate_by_span)
4. "kafka"         - Kafka health (consumer_lag, topic_partition_health, broker_health, message_rate, isr_status)
5. "kubernetes"    - Pods & Events (pod_status, restart_count, resource_limits, oom_kills, node_pressure, hpa_status)
6. "deployment"    - Changes & Releases (recent_releases, config_changes, feature_flags, rollback_history)"""

HYPOTHESES_PROMPT = """You are an SRE AI diagnosing a production alert.

{agents}

ALERT:
{alert}

Generate 2-4 plausible ROOT CAUSE hypotheses for this alert, ranked by likelihood.
Respond ONLY with valid JSON (no markdown):
{{
  "hypotheses": [
    {{
      "id": "H1",
      "statement": "<clear root-cause hypothesis>",
      "prior_confidence": <0.0-1.0>,
      "evidence_needed": ["<agent>.<check>", "<agent>.<check>"]
    }}
  ]
}}"""

PLAN_PROMPT = """You are an SRE AI in iteration {iteration} of {max_iterations} of a diagnostic loop.

{agents}

ALERT:
{alert}

CURRENT HYPOTHESES:
{hypotheses}

EVIDENCE COLLECTED SO FAR:
{evidence}

Plan the NEXT evidence collection round. Only request checks that would best confirm or reject the current hypotheses. Do NOT repeat checks already collected. Request at most {max_checks} checks.
Respond ONLY with valid JSON (no markdown):
{{
  "requests": [
    {{"agent": "<agent name>", "check": "<check name>", "target_hypothesis": "<H id>", "reason": "<why>"}}
  ]
}}"""

EVALUATE_PROMPT = """You are an SRE AI evaluating evidence in iteration {iteration} of a diagnostic loop.

ALERT:
{alert}

HYPOTHESES:
{hypotheses}

ALL EVIDENCE (including this round's new evidence):
{evidence}

For each hypothesis, update its confidence (0.0-1.0) based on the evidence. Mark each as "confirmed", "rejected", or "inconclusive". You may REFINE a hypothesis or ADD a new one (id H<n+1>) if evidence suggests a cause not yet considered.
Respond ONLY with valid JSON (no markdown):
{{
  "hypotheses": [
    {{"id": "H1", "statement": "<possibly refined>", "confidence": <0.0-1.0>, "status": "confirmed|rejected|inconclusive", "supporting_evidence": ["<evidence summary>"]}}
  ],
  "conclusion_ready": <true|false>,
  "reasoning": "<brief explanation of your evaluation>"
}}"""

CONCLUDE_PROMPT = """You are an SRE AI concluding a diagnostic investigation.

ALERT:
{alert}

FINAL HYPOTHESES:
{hypotheses}

ALL EVIDENCE:
{evidence}

Produce the final root cause analysis. Respond ONLY with valid JSON (no markdown):
{{
  "root_cause": "<the confirmed or most likely root cause>",
  "confidence": <0.0-1.0>,
  "impact": "<impact assessment>",
  "recommended_actions": ["<action 1>", "<action 2>"],
  "rollback_plan": "<how to revert if remediation fails>",
  "unresolved_questions": ["<anything still unknown>"]
}}"""


def _parse_json(raw: str) -> Dict[str, Any]:
    """Best-effort JSON extraction from an LLM response."""
    raw = raw.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        if raw.rstrip().endswith("```"):
            raw = raw.rstrip()[:-3]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(raw[start:end])
        logger.error(f"Unparseable LLM response: {raw[:500]!r}")
        raise


class EvidenceProvider:
    """Interface: collect evidence for a list of check requests."""

    async def collect(self, incident_id: str, requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        raise NotImplementedError


class HTTPEvidenceProvider(EvidenceProvider):
    """Calls the real fixora-diagnostic-orchestrator-agent to collect evidence."""

    def __init__(self, base_url: str):
        self.base_url = base_url

    async def collect(self, incident_id: str, requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/collect-evidence",
                json={"incident_id": incident_id, "requests": requests},
            )
            response.raise_for_status()
            return response.json().get("evidence", [])


class DiagnosticLoop:
    """
    Bounded iterative diagnostic reasoning loop.

    Bounds:
    - max_iterations: hard cap on hypothesis->evidence->replan cycles
    - confidence_threshold: exit early once a hypothesis is confirmed at/above this
    - max_checks_per_iteration: cap evidence requests per round (cost control)
    """

    def __init__(
        self,
        evidence_provider: EvidenceProvider,
        ollama_base_url: str = "http://localhost:11434",
        model: str = "qwen3:8b",
        max_iterations: int = 3,
        confidence_threshold: float = 0.8,
        max_checks_per_iteration: int = 4,
    ):
        self.evidence_provider = evidence_provider
        self.ollama_base_url = ollama_base_url
        self.model = model
        self.max_iterations = max_iterations
        self.confidence_threshold = confidence_threshold
        self.max_checks_per_iteration = max_checks_per_iteration

    async def run(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the bounded diagnostic loop. Returns final RCA + full trace."""
        incident_id = alert.get("alert_id", "unknown")
        alert_json = json.dumps(alert, indent=2)
        trace: List[Dict[str, Any]] = []
        all_evidence: List[Dict[str, Any]] = []
        collected_checks = set()

        # Step 1: initial hypotheses
        t0 = time.time()
        hyp_response = _parse_json(
            await self._call_llm(
                HYPOTHESES_PROMPT.format(agents=AVAILABLE_AGENTS_DESC, alert=alert_json)
            )
        )
        hypotheses = hyp_response.get("hypotheses", [])
        trace.append({
            "phase": "initial_hypotheses",
            "hypotheses": hypotheses,
            "duration_s": round(time.time() - t0, 1),
        })
        logger.info(f"[{incident_id}] Generated {len(hypotheses)} initial hypotheses")

        conclusion_ready = False

        # Step 2: bounded loop
        for iteration in range(1, self.max_iterations + 1):
            # 2a. Plan evidence collection
            t0 = time.time()
            plan = _parse_json(
                await self._call_llm(
                    PLAN_PROMPT.format(
                        iteration=iteration,
                        max_iterations=self.max_iterations,
                        agents=AVAILABLE_AGENTS_DESC,
                        alert=alert_json,
                        hypotheses=json.dumps(hypotheses, indent=2),
                        evidence=json.dumps(all_evidence, indent=2) or "none yet",
                        max_checks=self.max_checks_per_iteration,
                    )
                )
            )
            requests = plan.get("requests", [])[: self.max_checks_per_iteration]
            # Drop already-collected checks
            requests = [
                r for r in requests
                if (r.get("agent"), r.get("check")) not in collected_checks
            ]

            # 2b. Collect evidence
            new_evidence = await self.evidence_provider.collect(incident_id, requests)
            for r in requests:
                collected_checks.add((r.get("agent"), r.get("check")))
            all_evidence.extend(new_evidence)

            # 2c. Evaluate & replan
            evaluation = _parse_json(
                await self._call_llm(
                    EVALUATE_PROMPT.format(
                        iteration=iteration,
                        alert=alert_json,
                        hypotheses=json.dumps(hypotheses, indent=2),
                        evidence=json.dumps(all_evidence, indent=2),
                    )
                )
            )
            hypotheses = evaluation.get("hypotheses", hypotheses)
            conclusion_ready = evaluation.get("conclusion_ready", False)

            trace.append({
                "phase": f"iteration_{iteration}",
                "evidence_requests": requests,
                "new_evidence": new_evidence,
                "evaluation": evaluation,
                "duration_s": round(time.time() - t0, 1),
            })

            top_confidence = max((h.get("confidence", 0) for h in hypotheses), default=0)
            logger.info(
                f"[{incident_id}] Iteration {iteration}: top confidence={top_confidence:.2f}, "
                f"conclusion_ready={conclusion_ready}"
            )

            # 2d. Exit conditions
            confirmed = any(
                h.get("status") == "confirmed" and h.get("confidence", 0) >= self.confidence_threshold
                for h in hypotheses
            )
            if confirmed or conclusion_ready:
                break

        # Step 3: final conclusion
        t0 = time.time()
        conclusion = _parse_json(
            await self._call_llm(
                CONCLUDE_PROMPT.format(
                    alert=alert_json,
                    hypotheses=json.dumps(hypotheses, indent=2),
                    evidence=json.dumps(all_evidence, indent=2),
                )
            )
        )
        trace.append({"phase": "conclusion", "duration_s": round(time.time() - t0, 1)})

        return {
            "incident_id": incident_id,
            "root_cause_analysis": conclusion,
            "final_hypotheses": hypotheses,
            "iterations_used": sum(1 for t in trace if t["phase"].startswith("iteration_")),
            "max_iterations": self.max_iterations,
            "evidence_collected": all_evidence,
            "trace": trace,
        }

    async def _call_llm(self, prompt: str) -> str:
        # /no_think disables qwen3 reasoning tokens; format=json forces valid JSON output
        async with httpx.AsyncClient(timeout=600.0) as client:
            response = await client.post(
                f"{self.ollama_base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt + "\n/no_think",
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.2, "num_predict": 4096},
                },
            )
            response.raise_for_status()
            raw = response.json()["response"]
            # Strip any residual <think>...</think> block
            if "<think>" in raw and "</think>" in raw:
                raw = raw.split("</think>", 1)[1]
            return raw.strip()
