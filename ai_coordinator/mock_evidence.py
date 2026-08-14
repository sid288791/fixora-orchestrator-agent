"""
MockEvidenceProvider - simulated diagnostic agent responses for testing the
DiagnosticLoop without real Grafana/Kibana/Kafka/K8s backends.

Simulated ground-truth scenario (for the Kafka CPU alert):
  A config change deployed 25 minutes ago enabled zstd compression level 19
  on kafka-broker-3, causing sustained CPU saturation. Consumer lag is a
  SYMPTOM, not the cause. The LLM should discover this only after checking
  the deployment agent - typically in iteration 2+ (proving the replan works).
"""

from typing import Any, Dict, List

from ai_coordinator.diagnostic_loop import EvidenceProvider

# (agent, check) -> simulated result
MOCK_EVIDENCE_DB: Dict[tuple, Dict[str, Any]] = {
    # --- Grafana: CPU is genuinely high, mostly in compression threads ---
    ("grafana", "cpu_usage"): {
        "finding": "CPU on kafka-broker-3 at 92-95% sustained for 25 min. Breakdown: 71% in kafka-compression threads, 12% GC, 9% request handlers.",
        "anomaly": True,
    },
    ("grafana", "cpu_usage_trend"): {
        "finding": "CPU jumped from steady 45% to 92% at 07:20 UTC in a step change (not gradual).",
        "anomaly": True,
    },
    ("grafana", "memory_usage"): {
        "finding": "Heap usage normal at 58%. No memory pressure.",
        "anomaly": False,
    },
    ("grafana", "gc_activity"): {
        "finding": "GC pause times normal (avg 12ms). No GC storms.",
        "anomaly": False,
    },
    ("grafana", "disk_io"): {
        "finding": "Disk write throughput DOWN 40% since 07:20 UTC despite same message rate (smaller batches on disk).",
        "anomaly": True,
    },
    ("grafana", "throughput"): {
        "finding": "Producer throughput unchanged at ~85K msg/s. No traffic spike.",
        "anomaly": False,
    },
    ("grafana", "network"): {
        "finding": "Network I/O normal, no saturation.",
        "anomaly": False,
    },
    ("grafana", "latency_p99"): {
        "finding": "Produce request p99 latency up from 8ms to 210ms since 07:20 UTC.",
        "anomaly": True,
    },
    # --- Kafka agent: lag exists but is a downstream symptom ---
    ("kafka", "consumer_lag"): {
        "finding": "Consumer lag growing on 3 consumer groups reading from broker-3-led partitions. Lag started AFTER 07:20 UTC.",
        "anomaly": True,
    },
    ("kafka", "topic_partition_health"): {
        "finding": "All partitions healthy, no under-replicated partitions, leadership balanced.",
        "anomaly": False,
    },
    ("kafka", "broker_health"): {
        "finding": "Broker-3 alive, responding slowly to produce requests. Brokers 1,2,4,5 normal at 40-48% CPU.",
        "anomaly": True,
    },
    ("kafka", "message_rate"): {
        "finding": "Inbound message rate flat at ~85K msg/s for the last 6 hours. No traffic anomaly.",
        "anomaly": False,
    },
    ("kafka", "isr_status"): {
        "finding": "ISR stable, no shrinking.",
        "anomaly": False,
    },
    # --- Kubernetes: pod is fine, no resource limit issue ---
    ("kubernetes", "pod_status"): {
        "finding": "kafka-broker-3-0 Running, 0 restarts, no OOM kills, no evictions.",
        "anomaly": False,
    },
    ("kubernetes", "restart_count"): {
        "finding": "0 restarts in the last 7 days.",
        "anomaly": False,
    },
    ("kubernetes", "resource_limits"): {
        "finding": "CPU limit 8 cores, currently consuming 7.4. Limit unchanged for 90 days.",
        "anomaly": False,
    },
    ("kubernetes", "oom_kills"): {
        "finding": "No OOM kills.",
        "anomaly": False,
    },
    ("kubernetes", "node_pressure"): {
        "finding": "worker-node-12 healthy, no CPU/memory/disk pressure from other pods.",
        "anomaly": False,
    },
    ("kubernetes", "hpa_status"): {
        "finding": "No HPA configured for the Kafka StatefulSet.",
        "anomaly": False,
    },
    # --- Deployment: THE ROOT CAUSE ---
    ("deployment", "recent_releases"): {
        "finding": "No application releases to messaging namespace in the last 24h.",
        "anomaly": False,
    },
    ("deployment", "config_changes"): {
        "finding": "CONFIG CHANGE at 07:18 UTC: kafka-broker-3 broker config updated - 'compression.type' changed from lz4 to zstd with compression level 19 (ticket OPS-4412, applied by config-sync). Other brokers NOT yet updated (canary rollout).",
        "anomaly": True,
    },
    ("deployment", "feature_flags"): {
        "finding": "No feature flag changes in the last 48h.",
        "anomaly": False,
    },
    ("deployment", "rollback_history"): {
        "finding": "No rollbacks in the last 7 days. Config change OPS-4412 is revertible via config-sync.",
        "anomaly": False,
    },
    # --- Kibana: supporting log evidence ---
    ("kibana", "error_logs"): {
        "finding": "No ERROR-level logs. WARN logs since 07:20 UTC: 'request handler pool saturated' on broker-3.",
        "anomaly": True,
    },
    ("kibana", "container_logs"): {
        "finding": "Broker-3 logged 'Reconfiguring compression.type=zstd, level=19' at 07:18:42 UTC.",
        "anomaly": True,
    },
    ("kibana", "db_timeout_logs"): {
        "finding": "Not applicable to Kafka brokers.",
        "anomaly": False,
    },
    ("kibana", "oom_events"): {
        "finding": "No OOM events found.",
        "anomaly": False,
    },
    ("kibana", "exception_traces"): {
        "finding": "No exceptions in broker logs.",
        "anomaly": False,
    },
    # --- OpenTelemetry ---
    ("opentelemetry", "slowest_spans"): {
        "finding": "Slowest spans: kafka.produce on broker-3 partitions (p99 210ms vs 8ms baseline on other brokers).",
        "anomaly": True,
    },
    ("opentelemetry", "latency_breakdown"): {
        "finding": "Latency concentrated in broker-side processing (compression), not network or client.",
        "anomaly": True,
    },
    ("opentelemetry", "dependency_calls"): {
        "finding": "No downstream dependency slowness.",
        "anomaly": False,
    },
    ("opentelemetry", "error_rate_by_span"): {
        "finding": "No span error rate increase.",
        "anomaly": False,
    },
}


class MockEvidenceProvider(EvidenceProvider):
    """Returns canned evidence simulating the zstd-config-change scenario."""

    async def collect(self, incident_id: str, requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        evidence = []
        for req in requests:
            agent = (req.get("agent") or "").lower().strip()
            check = (req.get("check") or "").lower().strip()
            key = (agent, check)
            result = MOCK_EVIDENCE_DB.get(key)
            if result is None:
                # Fuzzy match: same agent, check name contains/contained
                for (db_agent, db_check), db_result in MOCK_EVIDENCE_DB.items():
                    if db_agent == agent and (db_check in check or check in db_check):
                        result = db_result
                        break
            if result is None:
                result = {"finding": f"No data available for {agent}.{check}", "anomaly": False}
            evidence.append({
                "agent": agent,
                "check": check,
                "target_hypothesis": req.get("target_hypothesis"),
                **result,
            })
        return evidence
