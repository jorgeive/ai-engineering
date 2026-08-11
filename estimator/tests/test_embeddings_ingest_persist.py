"""HTTP contract tests for the persistent embedding ingest endpoint."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_rag_ingest_service
from app.generation.rag.ingest_service import DuplicateDocumentError
from app.generation.rag.schemas import IngestResponse
from app.main import app


def budget_payload() -> dict:
    return {
        "budget_id": "BUD-2024-001",
        "client_metadata": {"name": "FintechCorp", "sector": "finance", "country": "ES"},
        "project_summary": "Mobile banking API with OAuth 2.0",
        "main_technology": "ruby_on_rails",
        "year": 2024,
        "total_estimated_hours": 120,
        "components": [{
            "component_id": "AUTH-001",
            "name": "OAuth 2.0 backend",
            "description": "OAuth flows with JWT session management.",
            "tech_stack": ["ruby_on_rails", "postgresql"],
            "estimated_hours": 120,
            "complexity": "high",
            "dependencies": [],
        }],
    }


def ingest_payload() -> dict:
    return {
        "source_path": "data/budgets/budget_2024_q1_fintech.json",
        "document_type": "historical_budget",
        "content": budget_payload(),
    }


class FakeRagIngestService:
    def __init__(self, duplicate_of: int | None = None) -> None:
        self.duplicate_of = duplicate_of
        self.calls: list[dict] = []

    async def ingest(self, *, source_path, document_type, budget) -> IngestResponse:
        self.calls.append({"source_path": source_path, "document_type": document_type, "budget": budget})
        if self.duplicate_of is not None:
            raise DuplicateDocumentError(self.duplicate_of)
        return IngestResponse(
            document_id=42,
            chunks_created=1,
            embedding_dimension=1536,
            ingestion_time_ms=12,
        )


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def test_ingest_returns_persistence_contract():
    fake = FakeRagIngestService()
    app.dependency_overrides[get_rag_ingest_service] = lambda: fake

    response = TestClient(app).post("/embeddings/ingest", json=ingest_payload())

    assert response.status_code == 200
    assert response.json() == {
        "document_id": 42,
        "chunks_created": 1,
        "embedding_dimension": 1536,
        "ingestion_time_ms": 12,
    }
    assert fake.calls[0]["budget"].budget_id == "BUD-2024-001"


def test_ingest_duplicate_returns_literal_409_shape():
    app.dependency_overrides[get_rag_ingest_service] = lambda: FakeRagIngestService(42)

    response = TestClient(app).post("/embeddings/ingest", json=ingest_payload())

    assert response.status_code == 409
    assert response.json() == {"detail": "Document already ingested", "document_id": 42}


def test_ingest_rejects_invalid_budget_before_service_call():
    fake = FakeRagIngestService()
    app.dependency_overrides[get_rag_ingest_service] = lambda: fake
    payload = ingest_payload()
    payload["content"].pop("components")

    response = TestClient(app).post("/embeddings/ingest", json=payload)

    assert response.status_code == 422
    assert fake.calls == []


def test_ingest_embedding_failure_returns_500():
    class ExplodingService(FakeRagIngestService):
        async def ingest(self, **kwargs):
            raise RuntimeError("embeddings API down")

    app.dependency_overrides[get_rag_ingest_service] = lambda: ExplodingService()

    response = TestClient(app).post("/embeddings/ingest", json=ingest_payload())

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to generate embeddings."
