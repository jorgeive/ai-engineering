"""Embed two texts and print their cosine similarity."""
from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.embedding_pipeline.embedder import OpenAIEmbedder  # noqa: E402


def cosine_similarity(vector_a: list[float], vector_b: list[float]) -> float:
    """Return cosine similarity using only Python's standard library."""

    if len(vector_a) != len(vector_b):
        raise ValueError("Embeddings must have the same dimension")

    dot_product = sum(value_a * value_b for value_a, value_b in zip(vector_a, vector_b))
    norm_a = math.sqrt(sum(value * value for value in vector_a))
    norm_b = math.sqrt(sum(value * value for value in vector_b))
    if norm_a == 0 or norm_b == 0:
        raise ValueError("Cosine similarity is undefined for a zero vector")
    return dot_product / (norm_a * norm_b)


def main() -> None:
    """Parse input texts, embed them, and print their similarity."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text-a", required=True, help="First text to compare.")
    parser.add_argument("--text-b", required=True, help="Second text to compare.")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        parser.error("OPENAI_API_KEY must be set in the environment or estimator/.env")

    embedder = OpenAIEmbedder(OpenAI(api_key=api_key))
    embedding_a = embedder.embed_one(args.text_a)
    embedding_b = embedder.embed_one(args.text_b)

    print(f"Text A: {args.text_a}")
    print(f"Text B: {args.text_b}")
    print(f"Cosine similarity: {cosine_similarity(embedding_a, embedding_b):.4f}")


if __name__ == "__main__":
    main()
