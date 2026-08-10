"""Run multi-turn memory stress scenarios and write one telemetry row per turn.

Run against a live estimator with, for example:

    uv run python -m evals.stress.run --http http://localhost:8000
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import time
from pathlib import Path
from typing import Any, cast

import httpx

from evals.stress.fixtures.build_pdfs import TARGETS_KB, main as build_pdfs
from evals.stress.metrics import (
    CostBudgetMetric,
    LatencyBudgetMetric,
    MemoryDriftMetric,
    TurnObserved,
)
from evals.stress.scenarios import Fact, SCENARIOS, ScenarioTurn


_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_CSV_COLUMNS = [
    "scenario",
    "attachment_size_kb",
    "repeat",
    "turn_index",
    "session_id",
    "enriched_transcript_chars",
    "attachments_total_chars",
    "messages_in_window",
    "anchors_count",
    "summary_chars",
    "tokens_in",
    "tokens_out",
    "cost_usd",
    "latency_ms",
    "wall_clock_ms",
    "cache_hit_kind",
    "last_resolved_tier",
    "latency_budget_passed",
    "cost_budget_passed",
    "memory_drift_passed",
    "tracked_facts",
    "error",
]
_SCENARIO_FORM_VALUES = {
    "growing": {"project_type": "web_saas"},
    "pivot": {"project_type": "mobile_app"},
    "contradiction": {"project_type": "internal_tool"},
}


def _ensure_fixtures(sizes_kb: list[int]) -> None:
    missing = [
        size for size in sizes_kb if size and not (_FIXTURES_DIR / f"attach_{size}kb.pdf").exists()
    ]
    unsupported = set(sizes_kb) - {0, *TARGETS_KB}
    if unsupported:
        raise ValueError(f"unsupported attachment sizes: {sorted(unsupported)}")
    if missing:
        build_pdfs()


def _files(size_kb: int) -> list[tuple[str, tuple[str, bytes, str]]] | None:
    if size_kb == 0:
        return None
    path = _FIXTURES_DIR / f"attach_{size_kb}kb.pdf"
    return [("attachments", (path.name, path.read_bytes(), "application/pdf"))]


def _form_data(scenario_name: str, transcript: str) -> dict[str, str]:
    return {
        "transcript": transcript,
        "detail_level": "medium",
        "output_format": "phases_table",
        **_SCENARIO_FORM_VALUES[scenario_name],
    }


async def _run_session(
    client: httpx.AsyncClient,
    *,
    scenario_name: str,
    turns: list[ScenarioTurn],
    size_kb: int,
    repeat: int,
    latency_metric: LatencyBudgetMetric,
    cost_metric: CostBudgetMetric,
    writer: csv.DictWriter,
) -> None:
    create_response = await client.post("/sessions")
    create_response.raise_for_status()
    session_id = create_response.json()["session_id"]
    prior_facts: list[Fact] = []

    for turn_index, transcript, fact_to_remember in turns:
        row: dict[str, Any] = {
            "scenario": scenario_name,
            "attachment_size_kb": size_kb,
            "repeat": repeat,
            "turn_index": turn_index,
            "session_id": session_id,
        }
        try:
            started = time.perf_counter()
            response = await client.post(
                f"/sessions/{session_id}/estimate",
                data=_form_data(scenario_name, transcript),
                files=_files(size_kb),
            )
            wall_clock_ms = int((time.perf_counter() - started) * 1000)
            response.raise_for_status()

            snapshot_response = await client.get(f"/sessions/{session_id}")
            snapshot_response.raise_for_status()
            snapshot = snapshot_response.json()
            raw_observation = snapshot.get("last_turn_observation")
            if raw_observation is None:
                raise RuntimeError("GET session did not return last_turn_observation")
            observation = cast(TurnObserved, raw_observation)

            latency_passed = latency_metric.evaluate(observation).passed
            cost_passed = cost_metric.evaluate(observation).passed
            drift_passed = all(
                MemoryDriftMetric(value, fact_field=field).evaluate(snapshot).passed
                for value, field in prior_facts
            )
            row.update(
                {
                    **observation,
                    "wall_clock_ms": wall_clock_ms,
                    "latency_budget_passed": latency_passed,
                    "cost_budget_passed": cost_passed,
                    "memory_drift_passed": drift_passed if prior_facts else "",
                    "tracked_facts": " | ".join(value for value, _field in prior_facts),
                    "error": "",
                }
            )
        except Exception as exc:  # noqa: BLE001
            row.update({"error": f"{type(exc).__name__}: {str(exc)[:200]}"})
            writer.writerow(row)
            return

        writer.writerow(row)
        if fact_to_remember:
            prior_facts.append(fact_to_remember)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--http", default="http://localhost:8000")
    parser.add_argument("--scenarios", default="growing,pivot,contradiction")
    parser.add_argument("--attachment-sizes", default="0,5,20,50,100")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--max-turns",
        type=int,
        default=7,
        help="Turns per session (default: 7, the first turn beyond the six-turn window).",
    )
    parser.add_argument("--latency-budget-ms", type=int, default=8_000)
    parser.add_argument("--cost-budget-usd", type=float, default=0.02)
    parser.add_argument("--output", type=Path, default=Path("evals/stress/results.csv"))
    args = parser.parse_args()

    scenario_names = [name.strip() for name in args.scenarios.split(",") if name.strip()]
    unknown = set(scenario_names) - SCENARIOS.keys()
    if unknown:
        raise ValueError(f"unknown scenarios: {sorted(unknown)}")
    sizes_kb = [int(size) for size in args.attachment_sizes.split(",")]
    if args.repeats < 1:
        raise ValueError("repeats must be at least one")
    if args.max_turns < 1:
        raise ValueError("max_turns must be at least one")
    _ensure_fixtures(sizes_kb)

    latency_metric = LatencyBudgetMetric(args.latency_budget_ms)
    cost_metric = CostBudgetMetric(args.cost_budget_usd)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(base_url=args.http, timeout=180.0) as client:
        with args.output.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=_CSV_COLUMNS)
            writer.writeheader()
            for scenario_name in scenario_names:
                for size_kb in sizes_kb:
                    for repeat in range(1, args.repeats + 1):
                        await _run_session(
                            client,
                            scenario_name=scenario_name,
                            turns=SCENARIOS[scenario_name][: args.max_turns],
                            size_kb=size_kb,
                            repeat=repeat,
                            latency_metric=latency_metric,
                            cost_metric=cost_metric,
                            writer=writer,
                        )
                        stream.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
