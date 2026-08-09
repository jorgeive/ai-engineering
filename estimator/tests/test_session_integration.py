from __future__ import annotations

from io import BytesIO
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_estimation_service
from app.main import app
from app.schemas.estimation import EstimationRequest, EstimationResponse, EstimationResult
from app.sessions import MAX_TURNS, SESSIONS


def _pdf_with_text(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    document = BytesIO(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(document.tell())
        document.write(f"{number} 0 obj\n".encode())
        document.write(obj)
        document.write(b"\nendobj\n")
    xref = document.tell()
    document.write(f"xref\n0 {len(objects) + 1}\n".encode())
    document.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        document.write(f"{offset:010d} 00000 n \n".encode())
    document.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode()
    )
    return document.getvalue()


def _response(summary: str) -> EstimationResponse:
    return EstimationResponse(
        result=EstimationResult(
            summary=summary,
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


class IntegrationService:
    def __init__(self) -> None:
        self.requests: list[EstimationRequest] = []
        self.messages: list[list[dict[str, str]]] = []

    def estimate(
        self,
        request: EstimationRequest,
        project_metadata=None,
        conversation_messages: list[dict[str, str]] | None = None,
    ) -> EstimationResponse:
        self.requests.append(request)
        self.messages.append(conversation_messages or [])
        if "PDF POLICY" in request.description:
            return _response("The estimate includes the PDF policy requirements.")
        return _response("The estimate uses the transcript only.")

    def estimate_conversational(
        self,
        request: EstimationRequest,
        project_metadata=None,
        conversation_messages: list[dict[str, str]] | None = None,
    ) -> EstimationResponse:
        return self.estimate(
            request,
            project_metadata=project_metadata,
            conversation_messages=conversation_messages,
        )


@pytest.fixture
def integration_service() -> IntegrationService:
    service = IntegrationService()
    app.dependency_overrides[get_estimation_service] = lambda: service
    SESSIONS.clear()
    yield service
    app.dependency_overrides.pop(get_estimation_service, None)
    SESSIONS.clear()


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.anyio
async def test_session_links_two_requests_and_updates_metadata(
    integration_service: IntegrationService,
) -> None:
    async with await _client() as client:
        created = await client.post("/sessions")
        session_id = created.json()["session_id"]
        assert UUID(session_id)

        await client.post(
            f"/sessions/{session_id}/estimate",
            data={"transcript": "Project: Atlas. Team of 3. Scope: scheduling with Python."},
        )
        await client.post(
            f"/sessions/{session_id}/estimate",
            data={"transcript": "Continue the React frontend and PostgreSQL integration."},
        )

        state = await client.get(f"/sessions/{session_id}")

    metadata = state.json()["project_metadata"]
    assert metadata["project_name"] == "Atlas"
    assert metadata["assumed_team_size"] == 3
    assert "Python" in metadata["mentioned_technologies"]
    assert "React" in metadata["mentioned_technologies"]
    assert len(integration_service.requests) == 2


@pytest.mark.anyio
async def test_pdf_attachment_changes_estimation_content(
    integration_service: IntegrationService,
) -> None:
    async with await _client() as client:
        first = await client.post(
            "/sessions/plain-session/estimate",
            data={"transcript": "Estimate the invoice approval portal."},
        )
        second = await client.post(
            "/sessions/pdf-session/estimate",
            data={"transcript": "Estimate the invoice approval portal."},
            files={"attachments": ("requirements.pdf", _pdf_with_text("PDF POLICY"), "application/pdf")},
        )

    assert "transcript only" in first.json()["result"]["summary"]
    assert "PDF policy" in second.json()["result"]["summary"]
    assert "--- attachment: requirements.pdf ---" in integration_service.requests[-1].description


@pytest.mark.anyio
async def test_eight_turns_never_send_more_than_configured_window(
    integration_service: IntegrationService,
) -> None:
    async with await _client() as client:
        created = await client.post("/sessions")
        session_id = created.json()["session_id"]
        for turn in range(8):
            response = await client.post(
                f"/sessions/{session_id}/estimate",
                data={"transcript": f"Please estimate turn number {turn} for the portal."},
            )
            assert response.status_code == 200

    assert all(len(messages) <= 1 + (MAX_TURNS * 2) for messages in integration_service.messages)
    assert all(messages[0]["role"] == "system" for messages in integration_service.messages)
    assert len(integration_service.messages[-1]) <= 1 + (MAX_TURNS * 2)
    last_contents = " ".join(message["content"] for message in integration_service.messages[-1])
    assert "turn number 0" not in last_contents
    assert "turn number 7" in last_contents
