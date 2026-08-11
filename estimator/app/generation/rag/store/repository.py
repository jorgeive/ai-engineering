"""Async persistence operations for documents and chunks."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.generation.rag.schemas import EmbeddedChunk
from app.generation.rag.store.models import ChunkRow, DocumentRow

BUDGET_COMPONENT = "budget_component"


class ChunkStore:
    async def find_document_id(self, session: AsyncSession, source_path: str) -> int | None:
        statement = select(DocumentRow.id).where(DocumentRow.source_path == source_path)
        return (await session.execute(statement)).scalar_one_or_none()

    async def create_document(
        self,
        session: AsyncSession,
        *,
        source_path: str,
        document_type: str,
        doc_metadata: dict,
    ) -> DocumentRow:
        document = DocumentRow(
            source_path=source_path,
            document_type=document_type,
            metadata_=doc_metadata,
        )
        session.add(document)
        await session.flush()

        return document

    async def add_chunks(
        self,
        session: AsyncSession,
        *,
        document_id: int,
        embedded_chunks: list[EmbeddedChunk],
    ) -> None:
        session.add_all(
            ChunkRow(
                document_id=document_id,
                chunk_type=BUDGET_COMPONENT,
                content=chunk.text,
                embedding=chunk.embedding,
                metadata_=chunk.metadata,
            )
            for chunk in embedded_chunks
        )

    async def search(
        self, session: AsyncSession, *, query_vector: list[float], k: int
    ) -> list:
        distance = ChunkRow.embedding.cosine_distance(query_vector)
        statement = (
            select(
                ChunkRow.id,
                ChunkRow.document_id,
                ChunkRow.chunk_type,
                ChunkRow.content,
                ChunkRow.metadata_,
                distance.label("distance"),
            )
            .order_by(distance)
            .limit(k)
        )
        return list((await session.execute(statement)).all())
