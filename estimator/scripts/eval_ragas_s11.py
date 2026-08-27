#!/usr/bin/env python3
"""Collect and score the Session 11 generation golden set with RAGAS."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.dependencies import get_embedder, get_token_encoder  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.generation.rag.context_assembler import build_context_block, truncate_to_token_budget  # noqa: E402
from app.generation.rag.estimator import generate_estimate  # noqa: E402
from app.generation.rag.query_reformulator import compose_search_text, reformulate_query  # noqa: E402
from app.generation.rag.retrieval.pipeline import retrieve  # noqa: E402

GOLDEN = ROOT / "evals" / "golden_generation_s11.json"
METRICS = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]


def install_ragas_vertex_shim() -> None:
    """Satisfy RAGAS's optional Vertex import; the evaluation uses OpenAI only."""
    try:
        import langchain_community.chat_models.vertexai  # noqa: F401
        return
    except Exception:
        pass

    class UnavailableVertex:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("Vertex AI is not configured for this evaluation.")

    module = types.ModuleType("langchain_community.chat_models.vertexai")
    module.ChatVertexAI = UnavailableVertex
    sys.modules[module.__name__] = module


def render_answer(estimate) -> str:
    """Render the structured estimate as text for the RAGAS dataset."""
    if estimate.confidence == "insufficient":
        return f"Insufficient context: {estimate.insufficient_context_explanation or ''}".strip()
    lines = [f"Total: {estimate.total_engineer_days} engineer-days.", f"Confidence: {estimate.confidence}."]
    for module in estimate.modules:
        for task in module.tasks:
            effort = "unknown" if task.engineer_days is None else str(task.engineer_days)
            lines.append(f"{module.name} — {task.name}: {effort} engineer-days")
    return "\n".join(lines)


async def collect(item: dict, embedder) -> dict:
    settings = get_settings()
    query = await reformulate_query(item.get("transcript") or item["query"])
    search_text = compose_search_text(query)
    embedding = await asyncio.to_thread(embedder.embed_one, search_text)
    retrieval = await retrieve(
        query_embedding=embedding,
        query_text=search_text,
        search_mode="hybrid",
        rerank=True,
        top_k=settings.RETRIEVAL_TOP_K,
        recall_k=settings.RETRIEVAL_RECALL_TOP_K,
        rerank_top_n=settings.RERANK_TOP_N,
        distance_threshold=1.2,
        rrf_k=settings.RRF_K,
    )
    kept = truncate_to_token_budget(retrieval.chunks, settings.MAX_CONTEXT_TOKENS, get_token_encoder())
    estimate = await generate_estimate(build_context_block(kept), structured_query=query)
    return {
        "id": item["id"],
        "question": item["query"],
        "answer": render_answer(estimate),
        "contexts": [chunk.content for chunk in kept],
        "ground_truth": item["ground_truth"],
    }


def score(samples: list[dict], judge_model: str, embedding_model: str):
    """Run all four RAGAS metrics with an OpenAI judge and embeddings model."""
    install_ragas_vertex_shim()
    from datasets import Dataset
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from ragas import evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

    dataset = Dataset.from_list(samples)
    result = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=LangchainLLMWrapper(ChatOpenAI(model=judge_model, temperature=0)),
        embeddings=LangchainEmbeddingsWrapper(OpenAIEmbeddings(model=embedding_model)),
    )
    return result.to_pandas()


def markdown_table(samples: list[dict], frame) -> str:
    """Render one metric row per query plus an average baseline row."""
    header = "| query | " + " | ".join(METRICS) + " |"
    separator = "|---|" + "---|" * len(METRICS)
    rows = [header, separator]
    for index, sample in enumerate(samples):
        values = " | ".join(f"{float(frame.iloc[index][metric]):.3f}" for metric in METRICS)
        rows.append(f"| {sample['id']} | {values} |")
    averages = [sum(float(frame.iloc[i][metric]) for i in range(len(samples))) / len(samples) for metric in METRICS]
    rows.append("| **average** | " + " | ".join(f"{value:.3f}" for value in averages) + " |")
    return "\n".join(rows)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collect-only", metavar="PATH", help="Write RAGAS inputs without scoring.")
    parser.add_argument("--samples", metavar="PATH", help="Read previously collected samples.")
    parser.add_argument("--out", metavar="PATH", help="Write metric results as JSON.")
    args = parser.parse_args()
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    if args.samples:
        samples_payload = json.loads(Path(args.samples).read_text(encoding="utf-8"))
        samples = samples_payload["samples"] if isinstance(samples_payload, dict) else samples_payload
    else:
        embedder = get_embedder()
        if embedder is None:
            raise RuntimeError("Embedding service is unavailable; configure OPENAI_API_KEY.")
        samples = [await collect(item, embedder) for item in golden["queries"]]
    if args.collect_only:
        Path(args.collect_only).write_text(json.dumps({"samples": samples}, indent=2, ensure_ascii=False), encoding="utf-8")
        return
    frame = score(samples, golden.get("judge_model", "gpt-4o-mini"), "text-embedding-3-small")
    table = markdown_table(samples, frame)
    print("\n=== RAGAS generation baseline ===\n" + table)
    report = {
        "metrics": METRICS,
        "table_markdown": table,
        "per_query": [{"id": s["id"], **{m: float(frame.iloc[i][m]) for m in METRICS}} for i, s in enumerate(samples)],
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
