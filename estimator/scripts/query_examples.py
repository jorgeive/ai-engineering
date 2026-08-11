#!/usr/bin/env python3
"""Smoke test for the persisted semantic-search pipeline.

The script ingests the sample corpus idempotently and runs five representative
queries against ``POST /search``. Use ``ESTIMATOR_BASE_URL`` to override the
API URL; otherwise localhost and the Compose service alias are probed.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
CORPUS_PATH = ROOT / "data" / "budgets_sample.json"
CANDIDATE_BASE_URLS = ("http://localhost:8000", "http://estimator:8000")
TOP_K = 5
CONTENT_PREVIEW_CHARS = 120

QUERIES: list[tuple[str, str]] = [
    (
        "Componente directo conocido (sanity check)",
        "REST API development with JWT authentication for financial sector",
    ),
    (
        "Reformulación semántica",
        "secure backend service with token-based access control for banking applications",
    ),
    (
        "Dominio distinto",
        "mobile application for restaurant reservations",
    ),
    (
        "Consulta ambigua",
        "integration with external system",
    ),
    (
        "Consulta muy específica",
        "migration from monolith to microservices architecture using Kubernetes",
    ),
]


def resolve_base_url(client: httpx.Client) -> str:
    """Return the configured URL or the first reachable Compose/host URL."""
    explicit = os.environ.get("ESTIMATOR_BASE_URL")
    for base_url in (explicit,) if explicit else CANDIDATE_BASE_URLS:
        try:
            if client.get(f"{base_url}/health").status_code == 200:
                return base_url
        except httpx.TransportError:
            continue
    print(
        "ERROR: no estimator API reachable. Start Docker Compose or set "
        "ESTIMATOR_BASE_URL.",
        file=sys.stderr,
    )
    raise SystemExit(1)


def ingest_corpus(client: httpx.Client, base_url: str) -> None:
    """Persist one sample budget per document; 409 means already present."""
    budgets = json.loads(CORPUS_PATH.read_text())
    created = skipped = 0
    for budget in budgets:
        response = client.post(
            f"{base_url}/embeddings/ingest",
            json={
                "source_path": f"data/budgets_sample.json::{budget['budget_id']}",
                "document_type": "historical_budget",
                "content": budget,
            },
        )
        if response.status_code == 200:
            created += 1
        elif response.status_code == 409:
            skipped += 1
        else:
            print(
                f"ERROR ingesting {budget['budget_id']}: "
                f"{response.status_code} {response.text[:200]}",
                file=sys.stderr,
            )
            raise SystemExit(1)
    print(f"Corpus: {len(budgets)} budgets — {created} ingested, {skipped} already present.")


def run_queries(client: httpx.Client, base_url: str) -> None:
    for index, (label, query) in enumerate(QUERIES, start=1):
        response = client.post(f"{base_url}/search", json={"query": query, "k": TOP_K})
        response.raise_for_status()
        body = response.json()

        print(f"\n[{index}/5] {label}")
        print(f'    query: "{query}"')
        print(f"    search_time_ms: {body['search_time_ms']}")
        print(f"    {'chunk_id':>8}  {'distance':>8}  {'chunk_type':<18}  content")
        for hit in body["results"]:
            preview = " ".join(hit["content"].split())[:CONTENT_PREVIEW_CHARS]
            print(
                f"    {hit['chunk_id']:>8}  {hit['distance']:>8.4f}  "
                f"{hit['chunk_type']:<18}  {preview}"
            )


def main() -> int:
    with httpx.Client(timeout=120.0) as client:
        base_url = resolve_base_url(client)
        print(f"Estimator API: {base_url}")
        ingest_corpus(client, base_url)
        run_queries(client, base_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
