import pytest
from pydantic import ValidationError

from app.sessions import (
    SESSIONS,
    ConversationHistory,
    MAX_TURNS,
    ProjectMetadata,
    clear_session,
    get_session,
    update_project_metadata,
)
from app.schemas.estimation import EstimationRequest, OutputFormat, ProjectType, DetailLevel


def test_sliding_window_preserves_system_prompt() -> None:
    history = ConversationHistory(max_turns=2, system_prompt="You are an estimator.")
    for index in range(1, 4):
        history.add_message("user", f"question {index}")
        history.add_message("assistant", f"answer {index}")

    assert history.as_messages() == [
        {"role": "system", "content": "You are an estimator."},
        {"role": "user", "content": "question 2"},
        {"role": "assistant", "content": "answer 2"},
        {"role": "user", "content": "question 3"},
        {"role": "assistant", "content": "answer 3"},
    ]


def test_default_window_is_six_complete_turns() -> None:
    history = ConversationHistory(system_prompt="You are an estimator.")
    for index in range(MAX_TURNS + 1):
        history.add_message("user", f"question {index}")
        history.add_message("assistant", f"answer {index}")

    messages = history.to_messages_list()
    assert len(messages) == 1 + (MAX_TURNS * 2)
    assert messages[1]["content"] == "question 1"
    assert messages[-1]["content"] == "answer 6"


def test_to_messages_list_regenerates_system_with_current_metadata() -> None:
    history = ConversationHistory()
    history.prompt_request = EstimationRequest(
        description="A platform for coordinating volunteer shifts and events.",
        project_type=ProjectType.WEB_SAAS,
        detail_level=DetailLevel.MEDIUM,
        output_format=OutputFormat.NARRATIVE,
    )
    history.project_metadata.project_name = "Volunteer Hub"
    history.add_message("user", "Please estimate the first release.")

    messages = history.to_messages_list()

    assert messages[0]["role"] == "system"
    assert "project_name: Volunteer Hub" in messages[0]["content"]
    assert messages[-1]["content"] == "Please estimate the first release."


def test_project_metadata_validates_and_has_safe_defaults() -> None:
    metadata = ProjectMetadata(project_name="Booking app", mentioned_technologies=["FastAPI"])

    assert metadata.assumed_team_size is None
    assert metadata.agreed_scope is None
    assert metadata.mentioned_technologies == ["FastAPI"]

    with pytest.raises(ValidationError):
        ProjectMetadata(assumed_team_size=0)


def test_sessions_are_indexed_in_process_memory() -> None:
    SESSIONS.clear()


def test_metadata_heuristic_extracts_facts_without_llm_call() -> None:
    metadata = ProjectMetadata()

    update_project_metadata(
        metadata,
        "Project: Invoice Hub. Team of 4. Scope: approval workflow. "
        "Build with Python, FastAPI, PostgreSQL and Redis.",
    )

    assert metadata.project_name == "Invoice Hub"
    assert metadata.assumed_team_size == 4
    assert metadata.mentioned_technologies == ["Python", "FastAPI", "PostgreSQL", "Redis"]
    assert metadata.agreed_scope == "approval workflow. Build with Python, FastAPI, PostgreSQL and Redis."
    first = get_session("session-a", max_turns=3)
    assert get_session("session-a") is first
    assert get_session("session-b") is not first

    clear_session("session-a")
    assert "session-a" not in SESSIONS
    SESSIONS.clear()
