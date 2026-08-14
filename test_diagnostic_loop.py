"""
Test the bounded iterative diagnostic loop (hypothesis -> evidence -> replan).

Scenario: Kafka CPU high alert. Ground truth (hidden in mock evidence):
a zstd level-19 compression config change deployed at 07:18 UTC.
The LLM must iterate to discover it - consumer lag is a red herring symptom.

Usage:
    python test_diagnostic_loop.py
"""

import asyncio
import json

from ai_coordinator.diagnostic_loop import DiagnosticLoop
from ai_coordinator.mock_evidence import MockEvidenceProvider

ALERT = {
    "alert_id": "ALT-001",
    "alert_name": "HighCPUUtilization",
    "source": "Prometheus",
    "severity": "critical",
    "platform": "kafka",
    "service": "kafka-broker-3",
    "namespace": "messaging",
    "description": "CPU utilization on kafka-broker-3 has exceeded 92% for the last 10 minutes",
    "metric_value": "92.4%",
    "threshold": "85%",
    "labels": {
        "cluster": "prod-kafka-cluster",
        "pod": "kafka-broker-3-0",
        "node": "worker-node-12",
    },
    "timestamp": "2026-08-14T07:45:00Z",
}

SEP = "=" * 80
SUB = "-" * 70


def print_hypotheses(hypotheses, title):
    print(f"\n  🧠 {title}:")
    for h in hypotheses:
        conf = h.get("confidence", h.get("prior_confidence", 0))
        status = h.get("status", "new")
        print(f"     [{h.get('id')}] ({conf:.2f}, {status}) {h.get('statement')}")


async def main():
    loop = DiagnosticLoop(
        evidence_provider=MockEvidenceProvider(),
        ollama_base_url="http://localhost:11434",
        model="qwen3:8b",
        max_iterations=3,
        confidence_threshold=0.8,
        max_checks_per_iteration=4,
    )

    print(f"\n{SEP}")
    print("  BOUNDED DIAGNOSTIC LOOP TEST  (hypothesis -> evidence -> replan)")
    print("  LLM: qwen3:8b | max_iterations=3 | confidence_threshold=0.8 | max_checks/iter=4")
    print(f"{SEP}")
    print(f"\n  🚨 ALERT: {ALERT['alert_name']} on {ALERT['service']} ({ALERT['metric_value']})")
    print(f"  Hidden ground truth: zstd level-19 config change at 07:18 UTC (deployment agent)")

    result = await loop.run(ALERT)

    for step in result["trace"]:
        phase = step["phase"]
        if phase == "initial_hypotheses":
            print(f"\n{SUB}")
            print(f"  PHASE 0: INITIAL HYPOTHESES  ({step['duration_s']}s)")
            print_hypotheses(step["hypotheses"], "Generated hypotheses")

        elif phase.startswith("iteration_"):
            n = phase.split("_")[1]
            print(f"\n{SUB}")
            print(f"  ITERATION {n}  ({step['duration_s']}s)")

            print(f"\n  🔍 Evidence requested:")
            for r in step["evidence_requests"]:
                print(f"     • {r.get('agent')}.{r.get('check')}  [-> {r.get('target_hypothesis')}]  {r.get('reason', '')}")

            print(f"\n  📦 Evidence returned:")
            for e in step["new_evidence"]:
                flag = "⚠️ " if e.get("anomaly") else "  "
                print(f"     {flag}{e['agent']}.{e['check']}: {e['finding'][:120]}")

            ev = step["evaluation"]
            print_hypotheses(ev.get("hypotheses", []), "Updated hypotheses after evaluation")
            print(f"\n  💭 Reasoning: {ev.get('reasoning', 'N/A')[:300]}")
            print(f"  ✅ Conclusion ready: {ev.get('conclusion_ready')}")

    rca = result["root_cause_analysis"]
    print(f"\n{SEP}")
    print("  FINAL ROOT CAUSE ANALYSIS")
    print(f"{SEP}")
    print(f"\n  🎯 Root Cause : {rca.get('root_cause')}")
    print(f"  📊 Confidence : {rca.get('confidence')}")
    print(f"  💥 Impact     : {rca.get('impact')}")
    print(f"\n  🛠  Recommended actions:")
    for a in rca.get("recommended_actions", []):
        print(f"     • {a}")
    print(f"\n  ↩️  Rollback plan: {rca.get('rollback_plan')}")
    if rca.get("unresolved_questions"):
        print(f"\n  ❓ Unresolved:")
        for q in rca["unresolved_questions"]:
            print(f"     • {q}")

    print(f"\n  Iterations used: {result['iterations_used']}/{result['max_iterations']}")
    print(f"  Evidence items collected: {len(result['evidence_collected'])}")
    print(f"{SEP}\n")

    with open("/tmp/diagnostic_loop_result.json", "w") as f:
        json.dump(result, f, indent=2)
    print("  Full trace saved to /tmp/diagnostic_loop_result.json\n")


if __name__ == "__main__":
    asyncio.run(main())
