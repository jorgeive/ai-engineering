"""Volatile, process-local session state for conversational estimations.

Sessions deliberately live in a plain dictionary for this stage of the course:
the API is single-process and the state is only conversational context, not
durable business data. A restart, deploy, or second worker may lose it; a later
exercise can replace this module with a shared store without changing callers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

MAX_TURNS = 6
MessageRole = Literal["system", "user", "assistant"]
Message = dict[str, str]


class ProjectMetadata(BaseModel):
    """Facts collected during a session; intentionally not persisted yet."""

    project_name: str | None = None
    assumed_team_size: int | None = Field(default=None, ge=1)
    mentioned_technologies: list[str] = Field(default_factory=list)
    agreed_scope: str | None = None


class SessionResponse(BaseModel):
    """Response returned when a new in-memory session is created."""

    session_id: UUID


class SessionStateResponse(BaseModel):
    """Debug view of the current volatile metadata and history size."""

    session_id: str
    project_metadata: ProjectMetadata
    message_count: int


@dataclass
class ConversationHistory:
    """Bounded conversation messages with a sliding window.

    ``max_turns`` counts user/assistant message pairs. The system prompt is
    kept outside that budget and is always retained as the first message.
    """

    max_turns: int = MAX_TURNS
    system_prompt: str | None = None
    project_metadata: ProjectMetadata = field(default_factory=ProjectMetadata)
    prompt_request: object | None = None
    messages: list[Message] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.max_turns < 1:
            raise ValueError("max_turns must be at least 1")
        if self.system_prompt is not None:
            self.messages = [
                {"role": "system", "content": self.system_prompt},
                *[message for message in self.messages if message.get("role") != "system"],
            ]
        self._trim()

    def add_message(self, role: MessageRole, content: str) -> None:
        """Append a message and discard the oldest complete window overflow."""
        if role == "system":
            self.system_prompt = content
            self.messages = [
                {"role": "system", "content": content},
                *[message for message in self.messages if message.get("role") != "system"],
            ]
        else:
            self.messages.append({"role": role, "content": content})
        self._trim()

    def _trim(self) -> None:
        system = next(
            (message for message in self.messages if message.get("role") == "system"),
            None,
        )
        conversation = [
            message for message in self.messages if message.get("role") != "system"
        ]
        while len(conversation) > self.max_turns * 2:
            del conversation[:2]
        self.messages = ([system] if system else []) + conversation

    def to_messages_list(self) -> list[Message]:
        """Return messages ready for an LLM API call.

        When a typed prompt request is attached, the system message is rendered
        again so the current ``project_metadata`` is always reflected. The
        fallback keeps a manually supplied system prompt usable for callers
        that do not need versioned templates.
        """
        system_message = next(
            (message for message in self.messages if message.get("role") == "system"),
            None,
        )
        if self.prompt_request is not None:
            from app.prompts.loader import render_estimation_prompt

            system, _ = render_estimation_prompt(
                self.prompt_request,
                project_metadata=self.project_metadata,
            )
            system_message = {"role": "system", "content": system}

        conversation = [
            message.copy() for message in self.messages if message.get("role") != "system"
        ]
        return ([system_message] if system_message else []) + conversation

    def as_messages(self) -> list[Message]:
        """Backward-compatible alias for :meth:`to_messages_list`."""
        return self.to_messages_list()


@dataclass
class Session:
    """In-memory state for one session id.

    This volatility is intentional for the exercise: session context is a
    temporary UX aid, and introducing persistence before the multi-worker
    deployment design would add infrastructure without durable-data needs.
    """

    session_id: str
    history: ConversationHistory = field(default_factory=ConversationHistory)
    metadata: ProjectMetadata = field(default_factory=ProjectMetadata)

    def __post_init__(self) -> None:
        self.history.project_metadata = self.metadata


# Process-local registry. It is intentionally not Redis-backed or database-backed.
SESSIONS: dict[str, Session] = {}

_KNOWN_TECHNOLOGIES = (
    "Python",
    "FastAPI",
    "Django",
    "JavaScript",
    "TypeScript",
    "React",
    "Next.js",
    "Node.js",
    "Ruby on Rails",
    "PostgreSQL",
    "MySQL",
    "Redis",
    "Docker",
    "Kubernetes",
    "AWS",
    "Azure",
    "GCP",
    "Swift",
    "Kotlin",
)


def update_project_metadata(metadata: ProjectMetadata, interaction: str) -> ProjectMetadata:
    """Extract obvious facts from a new interaction without another LLM call.

    This cheap heuristic is deliberate for the current phase: metadata is
    helpful conversational context, but it does not justify doubling provider
    calls and latency on every turn. A later exercise can replace this seam with
    a structured extractor model.
    """
    project_match = re.search(
        r"(?:project\s+name|project|nombre\s+del\s+proyecto)\s*[:\-]\s*([^\n,.]+)",
        interaction,
        flags=re.IGNORECASE,
    )
    if project_match:
        metadata.project_name = project_match.group(1).strip()

    team_match = re.search(r"(?:team\s+of|team\s+size)\s*(\d+)", interaction, flags=re.IGNORECASE)
    if team_match:
        metadata.assumed_team_size = int(team_match.group(1))

    for technology in _KNOWN_TECHNOLOGIES:
        if re.search(rf"(?<!\w){re.escape(technology)}(?!\w)", interaction, flags=re.IGNORECASE):
            if technology not in metadata.mentioned_technologies:
                metadata.mentioned_technologies.append(technology)

    scope_match = re.search(
        r"(?:agreed\s+scope|in\s+scope|scope)\s*[:\-]\s*([^\n]+)",
        interaction,
        flags=re.IGNORECASE,
    )
    if scope_match:
        metadata.agreed_scope = scope_match.group(1).strip()

    return metadata


def get_session(session_id: str, *, max_turns: int = MAX_TURNS) -> Session:
    """Return an existing session or create it in the current process."""
    if not session_id:
        raise ValueError("session_id must not be empty")
    session = SESSIONS.get(session_id)
    if session is None:
        session = Session(
            session_id=session_id,
            history=ConversationHistory(max_turns=max_turns),
        )
        SESSIONS[session_id] = session
    return session


def clear_session(session_id: str) -> None:
    """Discard one volatile session if it exists."""
    SESSIONS.pop(session_id, None)
