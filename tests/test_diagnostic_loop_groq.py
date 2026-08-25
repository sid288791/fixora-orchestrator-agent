import pytest

from ai_coordinator.diagnostic_loop import DiagnosticLoop, EvidenceProvider

ALERT = {"alert_id": "ALT-001", "alert_name": "HighErrorRate", "service": "payment-service"}


class FakeEvidenceProvider(EvidenceProvider):
    def __init__(self):
        self.received_requests = []

    async def collect(self, incident_id, requests):
        self.received_requests.extend(requests)
        return [
            {"agent": r["agent"], "check": r["check"], "target_hypothesis": r.get("target_hypothesis"),
             "finding": "found something", "anomaly": True}
            for r in requests
        ]


def make_fake_llm(responses):
    calls = {"n": 0}

    async def fake_llm(prompt: str) -> str:
        response = responses[min(calls["n"], len(responses) - 1)]
        calls["n"] += 1
        return response

    return fake_llm, calls


@pytest.mark.asyncio
async def test_loop_uses_injected_llm_call_instead_of_ollama():
    responses = [
        '{"hypotheses": [{"id": "H1", "statement": "DB pool exhaustion", "prior_confidence": 0.7, "evidence_needed": ["kibana.error_logs"]}]}',
        '{"requests": [{"agent": "kibana", "check": "error_logs", "target_hypothesis": "H1", "reason": "check errors"}]}',
        '{"hypotheses": [{"id": "H1", "statement": "DB pool exhaustion", "confidence": 0.9, "status": "confirmed", "supporting_evidence": ["found something"]}], "conclusion_ready": true, "reasoning": "clear"}',
        '{"root_cause": "DB pool exhaustion", "confidence": 0.9, "impact": "elevated errors", "recommended_actions": ["scale pool"], "rollback_plan": "revert config", "unresolved_questions": []}',
    ]
    fake_llm, calls = make_fake_llm(responses)
    provider = FakeEvidenceProvider()
    loop = DiagnosticLoop(evidence_provider=provider, llm_call=fake_llm, available_agents=["kibana"])

    result = await loop.run(ALERT)

    assert calls["n"] == 4
    assert result["root_cause_analysis"]["root_cause"] == "DB pool exhaustion"
    assert provider.received_requests[0]["agent"] == "kibana"


@pytest.mark.asyncio
async def test_loop_filters_out_requests_for_agents_not_in_available_agents():
    responses = [
        '{"hypotheses": [{"id": "H1", "statement": "high CPU", "prior_confidence": 0.6, "evidence_needed": ["grafana.cpu_usage"]}]}',
        '{"requests": [{"agent": "grafana", "check": "cpu_usage", "target_hypothesis": "H1", "reason": "check cpu"}, {"agent": "kibana", "check": "error_logs", "target_hypothesis": "H1", "reason": "check errors"}]}',
        '{"hypotheses": [{"id": "H1", "statement": "high CPU", "confidence": 0.5, "status": "inconclusive", "supporting_evidence": []}], "conclusion_ready": true, "reasoning": "n/a"}',
        '{"root_cause": "unclear", "confidence": 0.5, "impact": "n/a", "recommended_actions": [], "rollback_plan": "n/a", "unresolved_questions": []}',
    ]
    fake_llm, _ = make_fake_llm(responses)
    provider = FakeEvidenceProvider()
    loop = DiagnosticLoop(evidence_provider=provider, llm_call=fake_llm, available_agents=["kibana"])

    await loop.run(ALERT)

    agents_asked = {r["agent"] for r in provider.received_requests}
    assert agents_asked == {"kibana"}
