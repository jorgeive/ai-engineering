"""Semantic retrieval over the pgvector store."""
from __future__ import annotations

import asyncio
import time

import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.generation.rag.embedding.embedder import OpenAIEmbedder
from app.generation.rag.schemas import SearchHit, SearchResponse
from app.generation.rag.store.repository import ChunkStore

log = structlog.get_logger()


class SemanticRetriever:
    def __init__(
        self,
        embedder: OpenAIEmbedder,
        session_factory: async_sessionmaker,
        store: ChunkStore,
    ) -> None:
        self._embedder = embedder
        self._session_factory = session_factory
        self._store = store

    async def search(self, *, query: str, k: int) -> SearchResponse:
        started = time.perf_counter()
        query_vector = await asyncio.to_thread(self._embedder.embed_one, query)

        async with self._session_factory() as session:
            rows = await self._store.search(session, query_vector=query_vector, k=k)

        response = SearchResponse(
            query=query,
            k=k,
            search_time_ms=int((time.perf_counter() - started) * 1000),
            results=[
                SearchHit(
                    chunk_id=row.id,
                    document_id=row.document_id,
                    chunk_type=row.chunk_type,
                    content=row.content,
                    distance=float(row.distance),
                    metadata=row.metadata_,
                )
                for row in rows
            ],
        )
        log.info("rag_search_done", query=query[:80], k=k, results=len(response.results))
        return response
