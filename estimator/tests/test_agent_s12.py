from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from scripts.run_agent_s12 import TOOLS, run_agent


def test_tools_use_flat_responses_schema_and_strict_mode() -> None:
    assert [tool["name"] for tool in TOOLS] == ["search_budgets", "calculate_estimate"]
    assert all(tool["type"] == "function" and tool["strict"] is True for tool in TOOLS)
    assert all("function" not in tool for tool in TOOLS)
    assert TOOLS[0]["parameters"]["required"] == ["query", "filters"]
    assert TOOLS[1]["parameters"]["required"] == ["components"]


class FakeResponses:
    def __init__(self) -> None:
        self.calls = 0
        self.requests = []

    def create(self, **kwargs):
        self.calls += 1
        self.requests.append(kwargs)
        if self.calls == 1:
            return SimpleNamespace(
                id="r1",
                output=[
                    SimpleNamespace(
                        type="reasoning",
                        summary=[SimpleNamespace(text="I identified two distinct components.")],
                    ),
                    SimpleNamespace(
                        type="function_call",
                        name="search_budgets",
                        call_id="c1",
                        arguments=json.dumps({"query": "OAuth backend", "filters": None}),
                    ),
                ],
                output_text="",
            )
        if self.calls == 2:
            return SimpleNamespace(
                id="r2",
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="search_budgets",
                        call_id="c2",
                        arguments=json.dumps({"query": "mobile offline app", "filters": None}),
                    )
                ],
                output_text="",
            )
        if self.calls == 3:
            return SimpleNamespace(
                id="r3",
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="calculate_estimate",
                        call_id="c3",
                        arguments=json.dumps(
                            {
                                "components": [
                                    {"name": "OAuth backend", "reference_amounts": [420, 380]},
                                    {"name": "Mobile app", "reference_amounts": [780, 640]},
                                ]
                            }
                        ),
                    )
                ],
                output_text="",
            )
        return SimpleNamespace(
            id="r4",
            output=[],
            output_text="Estimate complete: 1,495.0 hours.",
        )


def test_manual_loop_returns_estimate_and_trace() -> None:
    responses = FakeResponses()
    client = SimpleNamespace(responses=responses)

    result = run_agent(
        "The project needs an OAuth backend and a mobile app.",
        client=client,
        search=lambda query, filters: [
            {"estimated_hours": 420.0, "budget_id": query, "distance": 0.1}
        ],
    )

    assert responses.calls == 4
    assert responses.requests[0]["model"] == "gpt-5"
    assert responses.requests[0]["reasoning"]["effort"] == "medium"
    assert result["estimate"]["total_hours"] == 1276.5
    assert len(result["trace"]) == 3
    assert [item["action"]["name"] for item in result["trace"]] == [
        "search_budgets",
        "search_budgets",
        "calculate_estimate",
    ]
    assert result["trace"][0]["reasoning"] == "I identified two distinct components."
    assert result["final_response"].startswith("Estimate complete")


def test_manual_loop_has_iteration_safety_limit() -> None:
    responses = FakeResponses()
    client = SimpleNamespace(responses=responses)

    with pytest.raises(RuntimeError, match="maximum of 2"):
        run_agent(
            "The project needs an OAuth backend and a mobile app.",
            client=client,
            max_iterations=2,
            search=lambda query, filters: [],
        )
