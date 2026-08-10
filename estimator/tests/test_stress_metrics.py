from __future__ import annotations

from evals.stress.metrics import (
    CostBudgetMetric,
    LatencyBudgetMetric,
    MemoryDriftMetric,
    TurnObserved,
)


def _observation(**overrides: object) -> TurnObserved:
    observation: TurnObserved = {
        "turn_index": 1,
        "session_id": "session-test",
        "enriched_transcript_chars": 120,
        "attachments_total_chars": 0,
        "messages_in_window": 2,
        "anchors_count": 0,
        "summary_chars": 0,
        "tokens_in": 500,
        "tokens_out": 300,
        "cost_usd": 0.002,
        "latency_ms": 1500,
        "cache_hit_kind": "none",
        "last_resolved_tier": "standard",
    }
    observation.update(overrides)  # type: ignore[arg-type]
    return observation


def test_latency_budget_passes_fails_and_accepts_the_boundary() -> None:
    metric = LatencyBudgetMetric(budget_ms=2_000)

    assert metric.evaluate(_observation(latency_ms=1_999)).passed is True
    assert metric.evaluate(_observation(latency_ms=2_001)).passed is False
    assert metric.evaluate(_observation(latency_ms=2_000)).passed is True


def test_cost_budget_passes_fails_and_accepts_the_boundary() -> None:
    metric = CostBudgetMetric(budget_usd=0.005)

    assert metric.evaluate(_observation(cost_usd=0.0049)).passed is True
    assert metric.evaluate(_observation(cost_usd=0.0051)).passed is False
    assert metric.evaluate(_observation(cost_usd=0.005)).passed is True


def test_memory_drift_passes_fails_and_matches_case_insensitively() -> None:
    metric = MemoryDriftMetric("Nimbus", fact_field="project_name")

    assert metric.evaluate({"metadata": {"project_name": "nimbus"}}).passed is True
    assert metric.evaluate({"metadata": {"project_name": "Atlas"}}).passed is False
    assert metric.evaluate({"metadata": {"project_name": "NIMBUS"}}).passed is True
