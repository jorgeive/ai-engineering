from fastapi.testclient import TestClient

from app.sessions import SESSIONS, get_session


def test_session_state_exposes_current_metadata(client: TestClient) -> None:
    SESSIONS.clear()
    session = get_session("debug-session")
    session.metadata.project_name = "Invoice Hub"
    session.history.add_message("user", "Estimate the approval workflow.")

    response = client.get("/sessions/debug-session")

    assert response.status_code == 200
    assert response.json()["project_metadata"]["project_name"] == "Invoice Hub"
    assert response.json()["message_count"] == 1
    SESSIONS.clear()
