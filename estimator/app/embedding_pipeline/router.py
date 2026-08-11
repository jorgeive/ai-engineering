"""HTTP routes for ingesting normalized budgets as embeddings."""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from openai import OpenAI

from app.dependencies import get_openai_client
from app.embedding_pipeline.chunker import JSONStructuralChunker
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.schemas import IngestRequest, IngestResponse

log = structlog.get_logger()

router = APIRouter(prefix="/embeddings", tags=["embeddings"])


@router.post("/ingest", response_model=IngestResponse)
def ingest_embeddings(
    request: IngestRequest,
    openai_client: OpenAI | None = Depends(get_openai_client),
) -> IngestResponse:
    """Chunk budgets, embed the chunks, and return the in-memory vectors."""

    if openai_client is None:
        log.error("embedding_ingestion_unavailable", reason="no_openai_api_key")
        raise HTTPException(status_code=500, detail="Embedding ingestion failed")

    log.info("embedding_ingestion_started", total_budgets=len(request.budgets))
    try:
        chunks = JSONStructuralChunker().chunk(request.budgets)
        embedder = OpenAIEmbedder(openai_client)
        embedded_chunks = embedder.embed_many(chunks)
        total_tokens = sum(chunk.token_count for chunk in chunks)
        response = IngestResponse(
            chunks=embedded_chunks,
            stats={
                "total_budgets": len(request.budgets),
                "total_chunks": len(embedded_chunks),
                "total_tokens": total_tokens,
                "estimated_cost_usd": embedder.estimated_cost_usd,
            },
        )
    except Exception as exc:  # noqa: BLE001 - upstream errors map to the HTTP contract.
        log.error(
            "embedding_ingestion_failed",
            error_type=type(exc).__name__,
            error=str(exc)[:400],
        )
        raise HTTPException(status_code=500, detail="Embedding ingestion failed") from exc

    log.info(
        "embedding_ingestion_completed",
        total_budgets=len(request.budgets),
        total_chunks=len(embedded_chunks),
        total_tokens=total_tokens,
        estimated_cost_usd=embedder.estimated_cost_usd,
    )
    return response
