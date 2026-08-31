"""Session 12: a manually driven Responses API tool-calling agent.

The model decomposes a transcript, searches each component independently, and
passes the retrieved reference amounts to a deterministic estimator.  The loop
is deliberately kept here (rather than delegated to an agent framework) so the
tool calls and observations can be inspected in the trace.

Examples, from the ``estimator`` directory::

    uv run python scripts/run_agent_s12.py exercises/session-12/sample_transcript_complex.txt
    uv run python scripts/run_agent_s12.py exercises/session-12/sample_transcript_complex.txt --stub
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openai import OpenAI  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.dependencies import get_embedder  # noqa: E402


SYSTEM_PROMPT = """You are a software estimation analyst.

Read the meeting transcript and turn it into a complete, structured estimate.
Use this method:
1. Identify every distinct in-scope software component. Do not merge separate
   components merely because they belong to the same project.
2. For each component, call search_budgets with a focused query describing its
   work. Make a separate search_budgets call for every component; never rely on
   one broad search for the whole transcript.
3. Use the returned historical items' estimated_hours as reference_amounts.
4. Call calculate_estimate once with all identified components and their
   reference amounts. If a component has no results, pass an empty list so the
   deterministic tool marks it unbudgeted.
5. In your final answer, report the structured breakdown and total from
   calculate_estimate, and mention any unbudgeted component. Do not invent
   amounts or perform arithmetic yourself.

You have exactly two tools: search_budgets retrieves historical evidence and
calculate_estimate performs the deterministic calculation. The transcript is
the source of scope; historical search results are the source of reference
amounts.
"""


TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "search_budgets",
        "description": (
            "Retrieve historical budget items relevant to one software component or "
            "requirement. Use this once per distinct component before estimating it. "
            "Search with the component's concrete capabilities, integrations, and "
            "technology terms; do not use this tool to calculate totals. Results "
            "contain historical estimated_hours and metadata that must be used as "
            "reference amounts."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Focused description of the component or requirement to find historical budgets for.",
                },
                "filters": {
                    "type": ["object", "null"],
                    "description": "Optional constraints for the historical search; use null when no constraint is justified.",
                    "properties": {
                        "component_type": {
                            "type": ["string", "null"],
                            "description": "Optional historical component category.",
                        },
                        "date_range": {
                            "type": ["object", "null"],
                            "description": "Optional inclusive year range for historical budgets.",
                            "properties": {
                                "from": {"type": ["integer", "null"]},
                                "to": {"type": ["integer", "null"]},
                            },
                            "required": ["from", "to"],
                            "additionalProperties": False,
                        },
                    },
                    "required": ["component_type", "date_range"],
                    "additionalProperties": False,
                },
            },
            "required": ["query", "filters"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "calculate_estimate",
        "description": (
            "Calculate a deterministic effort estimate from each component's name "
            "and historical reference amounts. It returns the per-component "
            "breakdown, a transparent contingency-adjusted estimate, and the total. "
            "Call it after searching all components; pass an empty reference_amounts "
            "array when evidence is missing rather than inventing a number."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "components": {
                    "type": "array",
                    "description": "All in-scope components and their historical estimated-hour references.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Human-readable component name."},
                            "reference_amounts": {
                                "type": "array",
                                "description": "Historical estimated-hour values retrieved for this component.",
                                "items": {"type": "number"},
                            },
                        },
                        "required": ["name", "reference_amounts"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["components"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


def _load_module(filename: str) -> Any:
    path = Path(__file__).parents[1] / "exercises/session-12" / filename
    spec = importlib.util.spec_from_file_location("session_12_reference_retrieval", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load retrieval stub from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_stub() -> Callable[[str, dict | None], list[dict[str, Any]]]:
    return _load_module("reference_retrieval.py").search_budgets_stub


def _real_search(query: str, filters: dict | None) -> list[dict[str, Any]]:
    """Adapt the existing S9–S10 hybrid/reranking pipeline to the tool contract."""
    from app.generation.rag.retrieval.collections import Collection
    from app.generation.rag.retrieval.pipeline import retrieve

    embedder = get_embedder()
    if embedder is None:
        raise RuntimeError("OPENAI_API_KEY is required for the real retrieval pipeline")
    settings = get_settings()
    query_text = query
    if filters and filters.get("component_type"):
        query_text = f"{query} component type: {filters['component_type']}"
    date_range = (filters or {}).get("date_range") or {}
    result = asyncio.run(
        retrieve(
            query_embedding=embedder.embed_one(query_text),
            query_text=query_text,
            search_mode=settings.RETRIEVAL_SEARCH_MODE,
            rerank=settings.RERANKER_ENABLED,
            top_k=settings.RETRIEVAL_TOP_K,
            recall_k=settings.RETRIEVAL_RECALL_TOP_K,
            rerank_top_n=settings.RERANK_TOP_N,
            distance_threshold=settings.RETRIEVAL_DISTANCE_THRESHOLD,
            rrf_k=settings.RRF_K,
            collection=Collection.BUDGET,
            project_year_min=date_range.get("from"),
            project_year_max=date_range.get("to"),
        )
    )
    return [
        {
            "id": hit.id,
            "content_preview": hit.content[:240],
            "sector": hit.sector,
            "budget_id": hit.budget_id,
            "estimated_hours": hit.estimated_hours,
            "distance": hit.distance,
            "project_year": hit.project_year,
        }
        for hit in result.chunks
    ]


def _reasoning_summary(response: Any) -> str:
    summaries: list[str] = []
    for item in response.output:
        if getattr(item, "type", None) != "reasoning":
            continue
        for summary in getattr(item, "summary", []) or []:
            text = getattr(summary, "text", None)
            if text:
                summaries.append(text)
    return " ".join(summaries) or "No reasoning summary was emitted by the model."


def run_agent(
    transcript: str,
    *,
    client: Any | None = None,
    model: str = "gpt-5",
    search: Callable[[str, dict | None], list[dict[str, Any]]] | None = None,
    max_iterations: int = 12,
) -> dict[str, Any]:
    """Run the manual tool loop and return the structured estimate plus trace.

    ``max_iterations`` limits model/tool round trips as a safety guard. Normal
    runs stop earlier when the model returns a response without function calls.
    """
    if max_iterations < 1:
        raise ValueError("max_iterations must be at least 1")
    client = client or OpenAI()
    search = search or _real_search
    calculate_estimate = _load_module("calculate_estimate_skeleton.py").calculate_estimate
    response = client.responses.create(
        model=model,
        instructions=SYSTEM_PROMPT,
        input=transcript,
        tools=TOOLS,
        reasoning={"effort": "medium", "summary": "auto"},
        parallel_tool_calls=False,
    )
    trace: list[dict[str, Any]] = []
    estimate: dict[str, Any] | None = None
    step = 0
    iterations = 0

    while True:
        calls = [item for item in response.output if getattr(item, "type", None) == "function_call"]
        if not calls:
            break
        iterations += 1
        if iterations > max_iterations:
            raise RuntimeError(
                f"Agent exceeded the maximum of {max_iterations} tool-loop iterations"
            )
        outputs = []
        for call in calls:
            args = json.loads(call.arguments)
            if call.name == "search_budgets":
                observation = search(args["query"], args.get("filters"))
            elif call.name == "calculate_estimate":
                observation = calculate_estimate(args)
                estimate = observation
            else:
                raise ValueError(f"Unknown function call: {call.name}")
            step += 1
            trace.append(
                {
                    "step": step,
                    "reasoning": _reasoning_summary(response),
                    "action": {"name": call.name, "arguments": args},
                    "observation": observation,
                }
            )
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(observation, ensure_ascii=False),
                }
            )
        response = client.responses.create(
            model=model,
            instructions=SYSTEM_PROMPT,
            previous_response_id=response.id,
            input=outputs,
            tools=TOOLS,
            reasoning={"effort": "medium", "summary": "auto"},
            parallel_tool_calls=False,
        )

    return {
        "estimate": estimate,
        "final_response": getattr(response, "output_text", ""),
        "trace": trace,
    }


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", type=Path)
    parser.add_argument("--model", default="gpt-5")
    parser.add_argument("--max-iterations", type=int, default=12)
    parser.add_argument("--stub", action="store_true", help="Use the safety-net canned retrieval corpus")
    args = parser.parse_args()
    result = run_agent(
        args.transcript.read_text(encoding="utf-8"),
        model=args.model,
        max_iterations=args.max_iterations,
        search=_load_stub() if args.stub else None,
    )
    for entry in result["trace"]:
        action = json.dumps(entry["action"], ensure_ascii=False)
        observation = json.dumps(entry["observation"], ensure_ascii=False)
        print(f"STEP {entry['step']} reasoning: {entry['reasoning']} action: {action} observation: {observation}")
    print("\nFINAL ESTIMATE")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _main()
