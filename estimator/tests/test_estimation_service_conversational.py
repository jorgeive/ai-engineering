from __future__ import annotations

from app.schemas.estimation import (
    DetailLevel,
    EstimationRequest,
    EstimationResult,
    OutputFormat,
    ProjectType,
)
from app.services.estimation import EstimationService


class CountingCache:
    def __init__(self) -> None:
        self.get_calls = 0
        self.set_calls = 0

    def get(self, _key: str):
        self.get_calls += 1
        return None

    def set(self, _key: str, _value) -> None:
        self.set_calls += 1


class CountingSemanticCache(CountingCache):
    def lookup(self, _request, _version):
        self.get_calls += 1
        return None

    def store(self, _request, _result, _version) -> None:
        self.set_calls += 1


class FakeWrapper:
    primary_model = "gpt-4o-mini"

    def __init__(self) -> None:
        self.calls = 0

    def complete_structured(self, **_kwargs):
        self.calls += 1
        return (
            EstimationResult(
                summary="A valid conversational estimate.",
                confidence_pct=80,
                phases=[
                    {
                        "name": "Discovery",
                        "duration_weeks": 1,
                        "cost_eur": 1000,
                        "summary": "Clarify scope and acceptance criteria.",
                    }
                ],
                total_duration_weeks=1,
                total_cost_eur=1000,
            ),
            {"model": "gpt-4o-mini", "provider": "fake", "latency_ms": 1},
        )


def _request() -> EstimationRequest:
    return EstimationRequest(
        description="Build a CRM for the sales team with contacts and reporting.",
        project_type=ProjectType.WEB_SAAS,
        detail_level=DetailLevel.MEDIUM,
        output_format=OutputFormat.NARRATIVE,
    )


def test_conversational_estimate_bypasses_both_caches() -> None:
    exact = CountingCache()
    semantic = CountingSemanticCache()
    wrapper = FakeWrapper()
    service = EstimationService(
        llm_wrapper=wrapper,
        exact_cache=exact,
        semantic_cache=semantic,
    )

    response = service.estimate_conversational(
        _request(),
        conversation_messages=[
            {"role": "system", "content": "system"},
            {"role": "user", "content": "transcript"},
        ],
    )

    assert response.cached is False
    assert wrapper.calls == 1
    assert exact.get_calls == exact.set_calls == 0
    assert semantic.get_calls == semantic.set_calls == 0
