"""Session 12 agent endpoint: transcript → tool-driven estimate + trace."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.rate_limiting import limiter
from app.api.security import require_estimate_key
from scripts.run_agent_s12 import run_agent

log = structlog.get_logger()
router = APIRouter(prefix="/v1/estimate", tags=["agent-estimate"])


class AgentEstimateRequest(BaseModel):
    """Transcript submitted by the business backend to the Session 12 agent."""

    transcript: str = Field(min_length=100, max_length=50_000)


class AgentEstimateResponse(BaseModel):
    """Structured deterministic estimate and the agent's ordered execution trace."""

    estimate: dict[str, Any] | None
    final_response: str
    trace: list[dict[str, Any]]


@router.post(
    "/agent/from-transcript",
    response_model=AgentEstimateResponse,
    dependencies=[Depends(require_estimate_key)],
)
@limiter.limit("10/minute")
async def agent_from_transcript(
    request: Request, payload: AgentEstimateRequest
) -> AgentEstimateResponse:
    """Run the manual tool-calling estimation loop inside the AI service."""
    try:
        result = await asyncio.to_thread(run_agent, payload.transcript)
        return AgentEstimateResponse(**result)
    except Exception as exc:  # noqa: BLE001 — map model/tool failures to 502.
        log.error("agent_estimate_failed", error_type=type(exc).__name__)
        raise HTTPException(status_code=502, detail="Failed to produce agent estimate.") from exc
