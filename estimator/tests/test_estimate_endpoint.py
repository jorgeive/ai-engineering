import pytest
from fastapi.testclient import TestClient

from app.services import llm_service


def _fake_response() -> dict:
    return {
        "estimation": "## Estimate\nA concise project estimate.",
        "model": "gpt-4o-mini",
        "provider": "openai",
        "finish_reason": "stop",
        "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
        "latency_ms": 12,
        "cost_usd": 0.001,
        "cache_hit": False,
    }


@pytest.fixture
def call_log(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls: list[dict] = []

    def fake(*, system_prompt: str, user_message: str, model_override: str | None,
             max_tokens: int, thinking_budget: int | None) -> dict:
        calls.append({"system_prompt": system_prompt, "user_message": user_message})
        return _fake_response()

    monkeypatch.setattr(llm_service, "_invoke_llm", fake)
    return calls


def test_estimate_returns_contract_response(client: TestClient, call_log: list[dict]) -> None:
    payload = {
        "description": "A booking platform for independent restaurants and their customers.",
        "project_type": "web_saas",
        "detail_level": "detailed",
        "output_format": "phases_table",
    }

    response = client.post("/api/v1/estimate", json=payload)

    assert response.status_code == 200
    assert response.json() == {
        "text": "## Estimate\nA concise project estimate.",
        "prompt_version": "v1",
    }
    assert "<project_description>" in call_log[0]["user_message"]
    assert payload["description"] in call_log[0]["user_message"]
    assert "Project type: web_saas" in call_log[0]["system_prompt"]
    assert "detailed breakdown" in call_log[0]["system_prompt"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("description", "too short"),
        ("description", "x" * 2001),
        ("project_type", "unsupported"),
        ("detail_level", "unsupported"),
        ("output_format", "unsupported"),
    ],
)
def test_estimate_rejects_invalid_contract_values(
    client: TestClient, field: str, value: str
) -> None:
    payload = {
        "description": "A valid project description that is long enough.",
        "project_type": "web_saas",
        "detail_level": "medium",
        "output_format": "narrative",
    }
    payload[field] = value

    response = client.post("/api/v1/estimate", json=payload)

    assert response.status_code == 422
