"""HTTP contract tests for semantic search."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_semantic_retriever
from app.generation.rag.schemas import SearchHit, SearchResponse
from app.main import app


class FakeRetriever:
    async def search(self, *, query: str, k: int) -> SearchResponse:
        return SearchResponse(
            query=query,
            k=k,
            search_time_ms=7,
            results=[
                SearchHit(
                    chunk_id=156,
                    document_id=12,
                    chunk_type="budget_component",
                    content="Backend service with JWT authentication.",
                    distance=0.231,
                    metadata={"scope": "backend", "technologies": ["python", "fastapi"]},
                )
            ],
        )


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def test_search_returns_ranked_result_contract():
    app.dependency_overrides[get_semantic_retriever] = lambda: FakeRetriever()

    response = TestClient(app).post(
        "/search",
        json={"query": "REST API with OAuth authentication for fintech sector", "k": 5},
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["distance"] == 0.231
    assert response.json()["results"][0]["chunk_id"] == 156


def test_search_rejects_invalid_k():
    app.dependency_overrides[get_semantic_retriever] = lambda: FakeRetriever()

    response = TestClient(app).post("/search", json={"query": "oauth", "k": 0})

    assert response.status_code == 422


def test_search_requires_embedder():
    app.dependency_overrides[get_semantic_retriever] = lambda: None

    response = TestClient(app).post("/search", json={"query": "oauth", "k": 5})

    assert response.status_code == 500
    assert response.json()["detail"] == "Embedding service is not available."
