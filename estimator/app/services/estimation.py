"""Pipeline orchestrator. Glue between guardrails, caches, prompt rendering and
the LLM wrapper. The router holds none of this logic — its only job is to
translate HTTP errors.

Pipeline (Session 4, final):

    1. Input guardrails (moderation + prompt injection + PII heuristics)
    2. Exact-match cache lookup  → return cached=True on hit
    3. Semantic cache lookup     → return cached=True on hit
    4. Render the versioned prompt
    5. LLM call via Instructor with response_model=EstimationResult
    6. Output guardrail (enforce_scope_response, filter policy)
    7. Write to BOTH caches (exact + semantic)
    8. Return EstimationResponse with cached=False

Order rationale: guardrails go before any cache because a malicious or PII
description should never be served from cache. The exact-match cache goes
before the semantic cache because it's the cheapest (no embedding call). The
semantic cache write happens AFTER output validation so we never cache failed
estimations.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import structlog

from app.cache.semantic import EstimationSemanticCache
from app.guardrails.input import check_input
from app.guardrails.output import enforce_scope_response
from app.prompts import render_estimation_prompt
from app.schemas.estimation import EstimationRequest, EstimationResponse, EstimationResult
from app.sessions import ProjectMetadata
from app.services.cache import EstimationCache
from app.services.llm_wrapper import LLMWrapper

log = structlog.get_logger()


def _exact_cache_key(
    request: EstimationRequest,
    prompt_version: str,
    model: str,
    project_metadata: ProjectMetadata | None = None,
    conversation_messages: list[dict[str, str]] | None = None,
) -> str:
    """Deterministic SHA-256 key over the typed request + prompt_version + model."""
    payload = json.dumps(
        {
            "description": request.description,
            "project_type": request.project_type.value,
            "detail_level": request.detail_level.value,
            "output_format": request.output_format.value,
            "prompt_version": prompt_version,
            "model": model,
            "project_metadata": (
                project_metadata.model_dump(mode="json") if project_metadata is not None else None
            ),
            "conversation_messages": conversation_messages,
        },
        sort_keys=True,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"estimation:v2:{digest}"


class EstimationService:
    """Single entry point for the structured estimation pipeline."""

    def __init__(
        self,
        *,
        llm_wrapper: LLMWrapper,
        exact_cache: EstimationCache,
        semantic_cache: EstimationSemanticCache | None = None,
        openai_client: Any | None = None,
        prompt_version: str = "v1",
    ) -> None:
        self.llm_wrapper = llm_wrapper
        self.exact_cache = exact_cache
        self.semantic_cache = semantic_cache
        self.openai_client = openai_client
        self.prompt_version = prompt_version

    def estimate(
        self,
        request: EstimationRequest,
        project_metadata: ProjectMetadata | None = None,
        conversation_messages: list[dict[str, str]] | None = None,
    ) -> EstimationResponse:
        # 1. Input guardrails — raises InputGuardrailViolation on rejection.
        check_input(request.description, openai_client=self.openai_client)

        # 2. Exact-match cache lookup.
        cache_key = _exact_cache_key(
            request,
            self.prompt_version,
            self.llm_wrapper.primary_model,
            project_metadata,
            conversation_messages,
        )
        cached = self.exact_cache.get(cache_key)
        if cached:
            log.info("estimation_cache_hit", kind="exact", key_prefix=cache_key[:24])
            result = EstimationResult.model_validate(cached["result"])
            return EstimationResponse(
                result=result, prompt_version=self.prompt_version, cached=True
            )

        # 3. Semantic cache lookup.
        has_metadata = _has_metadata(project_metadata)
        if self.semantic_cache is not None and not has_metadata:
            semantic_hit = self.semantic_cache.lookup(request, self.prompt_version)
            if semantic_hit is not None:
                log.info("estimation_cache_hit", kind="semantic")
                return EstimationResponse(
                    result=semantic_hit,
                    prompt_version=self.prompt_version,
                    cached=True,
                )

        # 4. Render the versioned prompt.
        system_prompt, user_message = render_estimation_prompt(
            request, version=self.prompt_version, project_metadata=project_metadata
        )

        # 5. LLM call with Instructor + Pydantic validators (re-prompts on failure).
        result, meta = self.llm_wrapper.complete_structured(
            system_prompt=system_prompt,
            user_message=user_message,
            messages=conversation_messages,
            response_model=EstimationResult,
        )
        log.info(
            "estimation_generated",
            prompt_version=self.prompt_version,
            confidence_pct=result.confidence_pct,
            total_cost_eur=result.total_cost_eur,
            phases=len(result.phases),
            **meta,
        )

        # 6. Output guardrail (filter): normalises low-confidence answers.
        result = enforce_scope_response(result)

        # 7. Cache the validated payload only (never persist failed validations).
        self.exact_cache.set(
            cache_key,
            {
                "result": result.model_dump(mode="json"),
                "prompt_version": self.prompt_version,
            },
        )
        if self.semantic_cache is not None and not has_metadata:
            self.semantic_cache.store(request, result, self.prompt_version)

        # 8. Return.
        return EstimationResponse(
            result=result, prompt_version=self.prompt_version, cached=False
        )

    def estimate_conversational(
        self,
        request: EstimationRequest,
        *,
        project_metadata: ProjectMetadata | None = None,
        conversation_messages: list[dict[str, str]] | None = None,
    ) -> EstimationResponse:
        """Estimate one session turn without consulting or mutating caches.

        A conversational turn is scoped by its session history and metadata;
        therefore an identical transcript in another session is not the same
        request.  The original :meth:`estimate` method remains the cached,
        stateless path used by ``/api/v1/estimate``.
        """
        check_input(request.description, openai_client=self.openai_client)
        system_prompt, user_message = render_estimation_prompt(
            request, version=self.prompt_version, project_metadata=project_metadata
        )
        result, meta = self.llm_wrapper.complete_structured(
            system_prompt=system_prompt,
            user_message=user_message,
            messages=conversation_messages,
            response_model=EstimationResult,
        )
        result = enforce_scope_response(result)
        log.info(
            "conversational_estimation_generated",
            confidence_pct=result.confidence_pct,
            total_cost_eur=result.total_cost_eur,
            phases=len(result.phases),
            **meta,
        )
        return EstimationResponse(
            result=result, prompt_version=self.prompt_version, cached=False
        )


def _has_metadata(metadata: ProjectMetadata | None) -> bool:
    if metadata is None:
        return False
    values = metadata.model_dump(exclude_none=True)
    return any(value not in ("", []) for value in values.values())
