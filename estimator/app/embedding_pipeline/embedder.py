"""OpenAI embedding client for budget chunks."""
from __future__ import annotations

import time
from typing import Any

import structlog
from openai import OpenAI, RateLimitError

from app.embedding_pipeline.schemas import Chunk, EmbeddedChunk

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_BATCH_SIZE = 100
# USD per 1M input tokens for text-embedding-3-small. Update when pricing changes.
EMBEDDING_PRICE_USD_PER_MILLION_INPUT_TOKENS = 0.02
RATE_LIMIT_RETRY_DELAYS_SECONDS = (1, 2, 4)

log = structlog.get_logger()


class OpenAIEmbedder:
    """Embed text with OpenAI, batching work to avoid serialized API calls."""

    def __init__(self, client: OpenAI) -> None:
        self._client = client
        self.estimated_cost_usd = 0.0

    def embed_one(self, text: str) -> list[float]:
        """Embed one text value with the configured embedding model."""

        response = self._create_embeddings([text])
        return list(response.data[0].embedding)

    def embed_many(self, chunks: list[Chunk]) -> list[EmbeddedChunk]:
        """Embed chunks in API batches and retain each chunk's metadata."""

        embedded_chunks: list[EmbeddedChunk] = []
        total_tokens = 0

        for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
            batch = chunks[start : start + EMBEDDING_BATCH_SIZE]
            batch_tokens = sum(chunk.token_count for chunk in batch)
            started_at = time.perf_counter()
            response = self._create_embeddings([chunk.text for chunk in batch])
            latency_ms = int((time.perf_counter() - started_at) * 1000)

            embeddings_by_index = {
                item.index: list(item.embedding)
                for item in response.data
            }
            embedded_chunks.extend(
                EmbeddedChunk(
                    **chunk.model_dump(),
                    embedding=embeddings_by_index[index],
                )
                for index, chunk in enumerate(batch)
            )
            total_tokens += batch_tokens
            log.info(
                "embedding_batch_processed",
                chunks_count=len(batch),
                total_tokens=batch_tokens,
                latency_ms=latency_ms,
            )

        self.estimated_cost_usd = round(
            total_tokens * EMBEDDING_PRICE_USD_PER_MILLION_INPUT_TOKENS / 1_000_000,
            6,
        )
        return embedded_chunks

    def _create_embeddings(self, texts: list[str]) -> Any:
        """Call OpenAI, retrying only transient rate-limit responses."""

        for retry_index, delay_seconds in enumerate(RATE_LIMIT_RETRY_DELAYS_SECONDS):
            try:
                return self._client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
            except RateLimitError:
                log.warning(
                    "embedding_rate_limited",
                    retry_number=retry_index + 1,
                    retry_delay_seconds=delay_seconds,
                )
                time.sleep(delay_seconds)

        return self._client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
