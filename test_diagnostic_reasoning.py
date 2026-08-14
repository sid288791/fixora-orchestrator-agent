"""
Test script: Send 4 mock alerts to the AI Coordinator (Ollama/qwen3:8b)
and print the diagnostic investigation plans.

LLM acts as the reasoning/planning brain to decide which diagnostic agents
need to be called for each alert type.

Usage:
    python test_diagnostic_reasoning.py
"""

import asyncio
import json
import sys

from ai_coordinator.coordinator import AICoordinator

# ─── 4 Mock Alerts ────────────────────────────────────────────────────────────

MOCK_ALERTS = [
    # Alert 1: Kafka CPU High
    {
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
    },
    # Alert 2: API Latency Spike on Payment Service
    {
        "alert_id": "ALT-002",
        "alert_name": "HighP99Latency",
        "source": "Grafana",
        "severity": "high",
        "platform": "application",
        "service": "payment-service",
        "namespace": "fintech",
        "description": "P99 latency for payment-service /api/v1/charge endpoint spiked to 4.5s (SLO: 500ms)",
        "metric_value": "4500ms",
        "threshold": "500ms",
        "labels": {
            "endpoint": "/api/v1/charge",
            "cluster": "prod-app-cluster",
            "pod": "payment-service-7d8f9-abcde",
        },
        "timestamp": "2026-08-14T08:10:00Z",
    },
    # Alert 3: Kubernetes Pod CrashLoopBackOff
    {
        "alert_id": "ALT-003",
        "alert_name": "PodCrashLoopBackOff",
        "source": "Prometheus",
        "severity": "critical",
        "platform": "kubernetes",
        "service": "order-processing-service",
        "namespace": "ecommerce",
        "description": "Pod order-processing-service-6c4b7-xyz is in CrashLoopBackOff state. Restarted 15 times in the last 30 minutes.",
        "metric_value": "15 restarts",
        "threshold": "3 restarts",
        "labels": {
            "pod": "order-processing-service-6c4b7-xyz",
            "cluster": "prod-k8s-cluster",
            "node": "worker-node-05",
            "container": "order-processor",
        },
        "timestamp": "2026-08-14T08:25:00Z",
    },
    # Alert 4: Kafka Consumer Lag on Notifications
    {
        "alert_id": "ALT-004",
        "alert_name": "KafkaConsumerLagHigh",
        "source": "Prometheus",
        "severity": "high",
        "platform": "kafka",
        "service": "notification-consumer",
        "namespace": "notifications",
        "description": "Consumer group 'notification-consumer-group' lag on topic 'user-notifications' has reached 500,000 messages and is growing",
        "metric_value": "500000 messages",
        "threshold": "10000 messages",
        "labels": {
            "consumer_group": "notification-consumer-group",
            "topic": "user-notifications",
            "cluster": "prod-kafka-cluster",
        },
        "timestamp": "2026-08-14T08:30:00Z",
    },
]

# ─── Formatting helpers ───────────────────────────────────────────────────────

SEPARATOR = "=" * 80
SUBSEP = "-" * 60


def print_alert_header(idx, alert):
    print(f"\n{SEPARATOR}")
    print(f"  ALERT {idx}: {alert['alert_name']}  |  Platform: {alert['platform']}  |  Severity: {alert['severity']}")
    print(f"  Service: {alert['service']}  |  Source: {alert['source']}")
    print(f"  Description: {alert['description']}")
    print(SEPARATOR)


def print_plan(plan):
    if "error" in plan:
        print(f"\n  ⚠ LLM Parse Error: {plan.get('error')}")
        print(f"  Raw: {plan.get('raw_response', '')[:500]}")
        return

    print(f"\n  📋 Alert Summary   : {plan.get('alert_summary', 'N/A')}")
    print(f"  🎯 Severity        : {plan.get('severity', 'N/A')}")
    print(f"  🖥  Affected Platform: {plan.get('affected_platform', 'N/A')}")
    print(f"  ⏱  Est. Time       : {plan.get('estimated_time_minutes', 'N/A')} minutes")

    agents = plan.get("diagnostic_agents_to_call", [])
    print(f"\n  🔍 Diagnostic Agents to Call ({len(agents)} platforms):")
    print(f"  {SUBSEP}")

    for agent in sorted(agents, key=lambda a: a.get("priority", 99)):
        print(f"\n    [{agent.get('priority', '?')}] {agent.get('agent', 'Unknown')}")
        print(f"        Reason: {agent.get('reason', 'N/A')}")
        checks = agent.get("checks", [])
        for check in checks:
            print(f"        • {check}")

    strategy = plan.get("investigation_strategy", "N/A")
    print(f"\n  📐 Investigation Strategy:")
    print(f"     {strategy}")


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main():
    coordinator = AICoordinator(
        ollama_base_url="http://localhost:11434",
        model="qwen3:8b",
    )

    print("\n" + SEPARATOR)
    print("  FIXORA DIAGNOSTIC REASONING TEST")
    print(f"  LLM Model: qwen3:8b (Ollama @ localhost:11434)")
    print(f"  Testing {len(MOCK_ALERTS)} mock alerts...")
    print(SEPARATOR)

    for idx, alert in enumerate(MOCK_ALERTS, 1):
        print_alert_header(idx, alert)
        print("\n  ⏳ Sending to LLM for diagnostic planning...")

        try:
            plan = await coordinator.plan_investigation(alert)
            print_plan(plan)
        except Exception as e:
            print(f"\n  ❌ Error: {e}")

    print(f"\n{SEPARATOR}")
    print("  TEST COMPLETE")
    print(SEPARATOR + "\n")


if __name__ == "__main__":
    asyncio.run(main())
