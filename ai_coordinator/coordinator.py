"""
AICoordinator - decides what to investigate, which diagnostic agents to use,
correlates evidence, and generates RCA & remediation options.

Uses a local LLM (Ollama) as the reasoning/planning brain to determine:
- Which diagnostic platforms need to be checked for a given alert
- What specific checks to run on each platform
- How to correlate evidence and synthesize root cause
"""

import json
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

DIAGNOSTIC_PLAN_PROMPT = """You are a Site Reliability Engineer (SRE) AI assistant working inside the Fixora incident management platform.

Given an alert, you must decide which diagnostic platforms/agents need to be called to investigate the issue.

Available diagnostic agents and what they provide:
1. **Grafana Agent** - Metrics & Dashboards (CPU, memory, disk, network, custom metrics)
2. **Kibana Agent** - Logs & Search (application logs, error logs, system logs)
3. **OpenTelemetry Agent** - Traces & Spans (distributed tracing, latency breakdown)
4. **Kafka Agent** - Consumer Lag, Topics, Brokers (Kafka-specific metrics and health)
5. **Kubernetes Agent** - Pods, Events, Deployments (pod status, restarts, resource limits)
6. **Deployment Agent** - Changes, Releases, Config (recent deployments, config changes)

For the given alert, respond ONLY with valid JSON (no markdown, no explanation outside JSON) in this exact format:
{
  "alert_summary": "<one line summary of the alert>",
  "severity": "<critical|high|medium|low>",
  "affected_platform": "<primary platform affected>",
  "diagnostic_agents_to_call": [
    {
      "agent": "<agent name>",
      "priority": <1-based priority order>,
      "checks": ["<specific check 1>", "<specific check 2>"],
      "reason": "<why this agent is needed>"
    }
  ],
  "investigation_strategy": "<brief strategy for correlating findings>",
  "estimated_time_minutes": <estimated investigation time>
}

ALERT:
"""


class AICoordinator:
    """
    AI Coordinator that uses a local LLM (Ollama/qwen3:8b) to reason about
    which diagnostic agents to call for a given alert.
    """

    def __init__(
        self,
        ollama_base_url: str = "http://localhost:11434",
        model: str = "qwen3:8b",
    ):
        self.ollama_base_url = ollama_base_url
        self.model = model

    async def plan_investigation(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send an alert to the LLM and get back a diagnostic investigation plan
        specifying which agents/platforms to call and what to check.
        """
        alert_text = json.dumps(alert, indent=2)
        prompt = DIAGNOSTIC_PLAN_PROMPT + alert_text

        raw_response = await self._call_llm(prompt)
        try:
            plan = json.loads(raw_response)
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            start = raw_response.find("{")
            end = raw_response.rfind("}") + 1
            if start != -1 and end > start:
                plan = json.loads(raw_response[start:end])
            else:
                plan = {"raw_response": raw_response, "error": "Failed to parse LLM response"}

        return plan

    async def correlate_evidence(self, evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Correlate evidence from multiple diagnostic agents to find root cause."""
        prompt = (
            "You are an SRE AI. Given the following evidence from multiple diagnostic agents, "
            "correlate the findings and identify the root cause. Respond in JSON with keys: "
            "root_cause, confidence, contributing_factors, timeline.\n\n"
            f"Evidence:\n{json.dumps(evidence, indent=2)}"
        )
        raw = await self._call_llm(prompt)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start != -1 and end > start:
                return json.loads(raw[start:end])
            return {"raw_response": raw}

    async def _call_llm(self, prompt: str) -> str:
        """Call the Ollama API with the given prompt."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.ollama_base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 2048,
                    },
                },
            )
            response.raise_for_status()
            return response.json()["response"]
