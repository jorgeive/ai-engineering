"""Endpoints for creating volatile conversation sessions."""

from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.sessions import SessionResponse, SessionStateResponse, get_session

router = APIRouter(tags=["sessions"])


@router.post("/sessions", response_model=SessionResponse)
def create_session() -> SessionResponse:
    """Create a process-local session and return its UUID for later requests."""
    session_id = uuid4()
    get_session(str(session_id))
    return SessionResponse(session_id=session_id)


@router.get("/sessions/{session_id}", response_model=SessionStateResponse)
def get_session_state(session_id: str) -> SessionStateResponse:
    """Return session metadata for the client's debugging panel."""
    try:
        session = get_session(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    return SessionStateResponse(
        session_id=session_id,
        project_metadata=session.metadata,
        message_count=len(session.history.messages),
    )
