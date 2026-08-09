from uuid import UUID

from fastapi.testclient import TestClient

from app.sessions import SESSIONS


def test_create_session_returns_uuid_and_registers_it(client: TestClient) -> None:
    SESSIONS.clear()

    response = client.post("/sessions")

    assert response.status_code == 200
    session_id = UUID(response.json()["session_id"])
    assert str(session_id) in SESSIONS


def test_create_session_returns_a_new_id_each_time(client: TestClient) -> None:
    first = client.post("/sessions").json()["session_id"]
    second = client.post("/sessions").json()["session_id"]

    assert first != second
