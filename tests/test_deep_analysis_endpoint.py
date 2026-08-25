from fastapi.testclient import TestClient

import server


class FakeDiagnosticLoop:
    async def run(self, alert):
        return {
            "incident_id": alert["alert_id"],
            "root_cause_analysis": {"root_cause": "DB pool exhaustion", "confidence": 0.9},
            "final_hypotheses": [],
            "iterations_used": 1,
            "max_iterations": 3,
            "evidence_collected": [],
        }


def test_deep_analysis_returns_diagnostic_loop_result(monkeypatch):
    monkeypatch.setattr(server, "build_diagnostic_loop", lambda: FakeDiagnosticLoop())
    client = TestClient(server.app)

    response = client.post("/api/v1/deep-analysis", json={
        "incident_id": "ALT-001",
        "alert_name": "HighErrorRate",
        "message": "Error rate spiked",
        "severity": "critical",
        "app_name": "payment-service",
        "existing_rca": "Likely a downstream dependency issue.",
    })

    assert response.status_code == 200
    body = response.json()
    assert body["root_cause_analysis"]["root_cause"] == "DB pool exhaustion"
