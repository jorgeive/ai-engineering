"""Deterministic metrics over per-turn stress-test telemetry and snapshots.

They live under ``evals.stress`` because their inputs are a ``turn_observed``
event and a conversational-session snapshot, rather than an EstimationResult.
``MetricResult`` remains shared with the normal evaluation suite so reports
have one result shape.
"""

from __future__ import annotations

import json
from typing import Any, Literal, TypedDict

from evals.metrics import MetricResult


FactField = Literal["project_name", "technologies", "scope", "summary", "any"]


class TurnObserved(TypedDict):
    """The fields emitted by ``EstimationService`` as ``turn_observed``."""

    turn_index: int
    session_id: str
    enriched_transcript_chars: int
    attachments_total_chars: int
    messages_in_window: int
    anchors_count: int
    summary_chars: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    cache_hit_kind: str
    last_resolved_tier: str | None


class LatencyBudgetMetric:
    name = "latency_budget"

    def __init__(self, budget_ms: int) -> None:
        if budget_ms <= 0:
            raise ValueError("budget_ms must be positive")
        self.budget_ms = budget_ms

    def evaluate(self, observation: TurnObserved) -> MetricResult:
        latency_ms = observation["latency_ms"]
        passed = latency_ms <= self.budget_ms
        return MetricResult(
            name=self.name,
            score=1.0 if passed else 0.0,
            passed=passed,
            details=f"{latency_ms} ms vs budget {self.budget_ms} ms",
        )


class CostBudgetMetric:
    name = "cost_budget"

    def __init__(self, budget_usd: float) -> None:
        if budget_usd <= 0:
            raise ValueError("budget_usd must be positive")
        self.budget_usd = budget_usd

    def evaluate(self, observation: TurnObserved) -> MetricResult:
        cost_usd = observation["cost_usd"]
        passed = cost_usd <= self.budget_usd
        return MetricResult(
            name=self.name,
            score=1.0 if passed else 0.0,
            passed=passed,
            details=f"${cost_usd:.6f} vs budget ${self.budget_usd:.6f}",
        )


class MemoryDriftMetric:
    """Check whether an earlier fact survives in a later session snapshot."""

    name = "memory_drift"

    def __init__(self, fact: str, fact_field: FactField = "any") -> None:
        if not fact:
            raise ValueError("fact must be a non-empty string")
        self.fact = fact
        self.fact_field = fact_field

    def evaluate(self, snapshot: dict[str, Any]) -> MetricResult:
        found = self.fact.casefold() in self._haystack(snapshot).casefold()
        return MetricResult(
            name=self.name,
            score=1.0 if found else 0.0,
            passed=found,
            details=(
                f"fact={self.fact!r} field={self.fact_field} "
                f"{'present' if found else 'missing'}"
            ),
        )

    def _haystack(self, snapshot: dict[str, Any]) -> str:
        metadata = snapshot.get("metadata") or {}
        if self.fact_field == "project_name":
            return str(metadata.get("project_name") or "")
        if self.fact_field == "technologies":
            return " ".join(metadata.get("mentioned_technologies") or [])
        if self.fact_field == "scope":
            return str(metadata.get("agreed_scope") or "")
        if self.fact_field == "summary":
            return str(snapshot.get("summary") or "")
        return json.dumps(snapshot, default=str, sort_keys=True)
