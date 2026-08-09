from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_estimation_service
from app.main import app
from app.schemas.estimation import EstimationRequest, EstimationResponse, EstimationResult
from app.sessions import SESSIONS, ProjectMetadata


def _response() -> EstimationResponse:
    return EstimationResponse(
        result=EstimationResult(
            summary="A valid estimate for the attached project requirements.",
            confidence_pct=80,
            phases=[
                {
                    "name": "Discovery",
                    "duration_weeks": 1,
                    "cost_eur": 1000,
                    "summary": "Clarify scope and acceptance criteria.",
                }
            ],
            total_duration_weeks=1,
            total_cost_eur=1000,
        ),
        prompt_version="v1",
    )


class FakeService:
    def __init__(self) -> None:
        self.requests: list[EstimationRequest] = []
        self.conversation_messages: list[list[dict[str, str]]] = []

    def estimate(
        self,
        request: EstimationRequest,
        project_metadata: ProjectMetadata | None = None,
        conversation_messages: list[dict[str, str]] | None = None,
    ) -> EstimationResponse:
        self.requests.append(request)
        self.conversation_messages.append(conversation_messages or [])
        return _response()

    def estimate_conversational(
        self,
        request: EstimationRequest,
        project_metadata: ProjectMetadata | None = None,
        conversation_messages: list[dict[str, str]] | None = None,
    ) -> EstimationResponse:
        return self.estimate(request, project_metadata, conversation_messages)


@pytest.fixture
def fake_service() -> FakeService:
    service = FakeService()
    app.dependency_overrides[get_estimation_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_estimation_service, None)


def test_session_estimate_extracts_and_separates_text_attachment(
    client: TestClient, fake_service: FakeService
) -> None:
    SESSIONS.clear()
    session_id = "session-with-attachment"

    response = client.post(
        f"/sessions/{session_id}/estimate",
        data={"transcript": "The client wants a portal for managing invoices and approvals."},
        files={"attachments": ("requirements.txt", b"Approvers are assigned per department.", "text/plain")},
    )

    assert response.status_code == 200
    assert len(fake_service.requests) == 1
    description = fake_service.requests[0].description
    assert "The client wants a portal" in description
    assert "--- attachment: requirements.txt ---" in description
    assert "Approvers are assigned per department." in description
    assert session_id in SESSIONS
    assert SESSIONS[session_id].history.messages[-2]["role"] == "user"
    SESSIONS.clear()


def test_session_estimate_rejects_unsupported_attachment(
    client: TestClient, fake_service: FakeService
) -> None:
    response = client.post(
        "/sessions/session-a/estimate",
        data={"transcript": "The client wants a portal for managing invoices and approvals."},
        files={"attachments": ("requirements.exe", b"binary", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert "Unsupported attachment type" in response.json()["detail"]
