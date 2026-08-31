from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.routers import agent_estimate
from app.main import app


def test_agent_endpoint_passes_transcript_to_service_agent(monkeypatch) -> None:
    captured = {}

    def fake_run_agent(transcript: str):
        captured["transcript"] = transcript
        return {"estimate": {"total_hours": 10}, "final_response": "ok", "trace": []}

    monkeypatch.setattr(agent_estimate, "run_agent", fake_run_agent)
    app.dependency_overrides[agent_estimate.require_estimate_key] = lambda: None
    with TestClient(app) as client:
        response = client.post(
            "/v1/estimate/agent/from-transcript",
            headers={"X-API-Key": "test-key"},
            json={"transcript": "A" * 120},
        )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert captured["transcript"] == "A" * 120
    assert response.json()["estimate"]["total_hours"] == 10
