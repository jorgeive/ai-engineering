"""HTTP endpoint for semantic search over persisted chunks."""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_semantic_retriever
from app.generation.rag.retriever import SemanticRetriever
from app.generation.rag.schemas import SearchRequest, SearchResponse

log = structlog.get_logger()
router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    retriever: SemanticRetriever | None = Depends(get_semantic_retriever),
) -> SearchResponse:
    if retriever is None:
        raise HTTPException(status_code=500, detail="Embedding service is not available.")
    try:
        return await retriever.search(query=request.query, k=request.k)
    except Exception as exc:  # noqa: BLE001 — infrastructure failures become a 500.
        log.error("search_failed", error_type=type(exc).__name__, error=str(exc)[:300])
        raise HTTPException(status_code=500, detail="Failed to run semantic search.") from exc
