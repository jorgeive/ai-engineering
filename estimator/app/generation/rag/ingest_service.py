"""Transactional chunk → embed → persist orchestration."""
from __future__ import annotations

import asyncio
import time

import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.generation.rag.chunking.structural import JSONStructuralChunker
from app.generation.rag.embedding.embedder import OpenAIEmbedder
from app.generation.rag.schemas import Budget, IngestResponse
from app.generation.rag.store.repository import ChunkStore

log = structlog.get_logger()


class DuplicateDocumentError(Exception):
    def __init__(self, document_id: int) -> None:
        self.document_id = document_id
        super().__init__(f"Document already ingested (id={document_id})")


class RagIngestService:
    def __init__(
        self,
        chunker: JSONStructuralChunker,
        embedder: OpenAIEmbedder,
        session_factory: async_sessionmaker,
        store: ChunkStore,
    ) -> None:
        self._chunker = chunker
        self._embedder = embedder
        self._session_factory = session_factory
        self._store = store

    async def ingest(self, *, source_path: str, document_type: str, budget: Budget) -> IngestResponse:
        started = time.perf_counter()
        async with self._session_factory() as session, session.begin():
            existing_id = await self._store.find_document_id(session, source_path)
            if existing_id is not None:
                raise DuplicateDocumentError(existing_id)

            document = await self._store.create_document(
                session,
                source_path=source_path,
                document_type=document_type,
                doc_metadata={
                    "budget_id": budget.budget_id,
                    "client_sector": budget.client_metadata.sector,
                    "year": budget.year,
                },
            )
            chunks = self._chunker.chunk([budget])
            embedded = await asyncio.to_thread(self._embedder.embed_many, chunks)
            await self._store.add_chunks(
                session,
                document_id=document.id,
                embedded_chunks=embedded,
            )

        response = IngestResponse(
            document_id=document.id,
            chunks_created=len(embedded),
            embedding_dimension=len(embedded[0].embedding) if embedded else 0,
            ingestion_time_ms=int((time.perf_counter() - started) * 1000),
        )
        log.info("rag_ingest_persisted", source_path=source_path, **response.model_dump())
        return response
