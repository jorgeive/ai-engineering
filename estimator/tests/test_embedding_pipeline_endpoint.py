"""HTTP tests for the in-memory budget embedding endpoint."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_openai_client
from app.main import app


class FakeOpenAIClient:
    """Minimal embeddings API double that records batched requests."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, list[str]]] = []
        self.embeddings = SimpleNamespace(create=self.create)

    def create(self, *, model: str, input: list[str]):
        self.requests.append((model, input))
        return SimpleNamespace(
            data=[
                SimpleNamespace(index=index, embedding=[float(index), 0.5])
                for index, _text in enumerate(input)
            ]
        )


@pytest.fixture
def embedding_client():
    fake_openai = FakeOpenAIClient()
    app.dependency_overrides[get_openai_client] = lambda: fake_openai
    with TestClient(app) as client:
        yield client, fake_openai
    app.dependency_overrides.clear()


def _sample_payload() -> dict:
    budgets_path = Path(__file__).parents[1] / "data" / "budgets_sample.json"
    return {"budgets": json.loads(budgets_path.read_text(encoding="utf-8"))}


def test_ingest_returns_embedded_chunks_and_stats(embedding_client) -> None:
    client, fake_openai = embedding_client

    response = client.post("/embeddings/ingest", json=_sample_payload())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["stats"]["total_budgets"] == 15
    assert body["stats"]["total_chunks"] == 52
    assert body["stats"]["total_tokens"] > 0
    assert body["stats"]["estimated_cost_usd"] > 0
    assert body["chunks"][0]["chunk_id"] == "BUD-2024-001::AUTH-001"
    assert body["chunks"][0]["embedding"] == [0.0, 0.5]
    assert [len(input) for _model, input in fake_openai.requests] == [52]


def test_ingest_validation_failure_returns_422(embedding_client) -> None:
    client, _fake_openai = embedding_client

    response = client.post("/embeddings/ingest", json={"budgets": []})

    assert response.status_code == 422


def test_ingest_upstream_failure_returns_generic_500(embedding_client) -> None:
    client, fake_openai = embedding_client

    def raise_upstream_error(*, model: str, input: list[str]):
        raise RuntimeError("provider diagnostic detail")

    fake_openai.embeddings.create = raise_upstream_error
    response = client.post("/embeddings/ingest", json=_sample_payload())

    assert response.status_code == 500
    assert response.json() == {"detail": "Embedding ingestion failed"}


def test_docs_include_embedding_ingestion_route(embedding_client) -> None:
    client, _fake_openai = embedding_client

    assert client.get("/docs").status_code == 200
    assert "/embeddings/ingest" in app.openapi()["paths"]
