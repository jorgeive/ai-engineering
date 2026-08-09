"""POST /api/v1/estimate — typed input, validated structured output.

Error handling mapping:

- ``InputGuardrailViolation`` → HTTP 400 with ``{reason, message}`` so the cliente
  can render a clear actionable message (the regex caught a prompt injection,
  PII, or moderation flagged the content).
- Anything else from the pipeline → HTTP 502 (the LLM upstream failed,
  including ``InstructorRetryException`` when the model couldn't satisfy
  validators within ``max_retries``).
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.attachments import extract_attachment_text
from app.dependencies import get_estimation_service
from app.guardrails.input import InputGuardrailViolation
from app.schemas.estimation import (
    DetailLevel,
    EstimationRequest,
    EstimationResponse,
    OutputFormat,
    ProjectType,
)
from app.sessions import get_session, update_project_metadata
from app.services.estimation import EstimationService

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["estimations"])
session_router = APIRouter(tags=["sessions"])


@router.post("/estimate", response_model=EstimationResponse)
def create_estimation(
    request: EstimationRequest,
    service: EstimationService = Depends(get_estimation_service),
) -> EstimationResponse:
    """Run the full estimation pipeline and return the structured response."""
    log.info(
        "estimation_request_received",
        project_type=request.project_type.value,
        detail_level=request.detail_level.value,
        output_format=request.output_format.value,
        description_chars=len(request.description),
    )

    try:
        return service.estimate(request)
    except InputGuardrailViolation as exc:
        log.info(
            "estimation_blocked_by_input_guardrail",
            reason=exc.reason,
            message=exc.message,
        )
        raise HTTPException(
            status_code=400, detail={"reason": exc.reason, "message": exc.message}
        ) from exc
    except Exception as exc:
        log.error(
            "estimation_endpoint_error",
            error=str(exc)[:400],
            error_type=type(exc).__name__,
        )
        raise HTTPException(status_code=502, detail="Upstream LLM call failed") from exc


@router.post("/sessions/{session_id}/estimate", response_model=EstimationResponse)
async def create_session_estimation(
    session_id: str,
    transcript: Annotated[str, Form(...)],
    attachments: Annotated[list[UploadFile] | None, File()] = None,
    service: EstimationService = Depends(get_estimation_service),
) -> EstimationResponse:
    """Estimate a transcript enriched with text extracted from attachments.

    This is path B: attachments never leave the service. Their extracted text
    is added to the transcript with a filename separator before estimation.
    """
    session = get_session(session_id)
    combined = transcript.strip()
    for attachment in attachments or []:
        try:
            extracted = await extract_attachment_text(attachment)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        filename = attachment.filename or "attachment"
        combined += f"\n\n--- attachment: {filename} ---\n{extracted}"

    try:
        request = EstimationRequest(
            description=combined,
            project_type=ProjectType.WEB_SAAS,
            detail_level=DetailLevel.MEDIUM,
            output_format=OutputFormat.NARRATIVE,
        )
        session.history.prompt_request = request
        session.history.add_message("user", combined)
        response = service.estimate_conversational(
            request,
            project_metadata=session.metadata,
            conversation_messages=session.history.to_messages_list(),
        )
        session.history.add_message("assistant", response.result.summary)
        interaction = "\n".join(
            [
                combined,
                response.result.summary,
                *(phase.summary for phase in response.result.phases),
            ]
        )
        update_project_metadata(session.metadata, interaction)
        return response
    except InputGuardrailViolation as exc:
        raise HTTPException(
            status_code=400, detail={"reason": exc.reason, "message": exc.message}
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        log.error("session_estimation_endpoint_error", error=str(exc)[:400])
        raise HTTPException(status_code=502, detail="Upstream LLM call failed") from exc


# Keep the exercise's unversioned path while the main API remains versioned.
session_router.add_api_route(
    "/sessions/{session_id}/estimate",
    create_session_estimation,
    methods=["POST"],
    response_model=EstimationResponse,
)
