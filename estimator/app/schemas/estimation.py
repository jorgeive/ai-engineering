"""Request and response models for the estimation endpoint.

Session 4 contract: typed form-style request maps to a typed, validated
``EstimationResult`` (structured output via Instructor + Pydantic). Two model
validators enforce business rules for the structured result:

1. The server derives ``total_cost_eur`` from the cost of all phases.
2. Low-confidence answers (< 30%) must declare it explicitly by starting the
   summary with ``"Out of scope:"``.

Malformed phase values still cause Instructor to re-prompt the model; simple
arithmetic mismatches are normalised before validation.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ProjectType(str, Enum):
    MOBILE_APP = "mobile_app"
    WEB_SAAS = "web_saas"
    INTERNAL_TOOL = "internal_tool"
    DATA_PIPELINE = "data_pipeline"


class DetailLevel(str, Enum):
    SUMMARY = "summary"
    MEDIUM = "medium"
    DETAILED = "detailed"


class OutputFormat(str, Enum):
    PHASES_TABLE = "phases_table"
    LINE_ITEMS = "line_items"
    NARRATIVE = "narrative"


class EstimationRequest(BaseModel):
    """Typed payload sent by the business backend or Streamlit form."""

    description: str = Field(
        min_length=20,
        max_length=80000,
        description="Free-text description or transcription of the project to estimate.",
    )
    project_type: ProjectType = Field(description="Coarse-grained project category.")
    detail_level: DetailLevel = Field(description="How deep the estimation should go.")
    output_format: OutputFormat = Field(description="Shape of the rendered estimation.")


# --- Structured response ----------------------------------------------------


OUT_OF_SCOPE_PREFIX = "Out of scope:"
LOW_CONFIDENCE_THRESHOLD = 30


class Phase(BaseModel):
    """One phase in the breakdown of an estimation."""

    name: str = Field(min_length=1, max_length=64)
    duration_weeks: int = Field(ge=1, le=52)
    cost_eur: int = Field(ge=0, le=1_000_000)
    summary: str = Field(min_length=10, max_length=600)


class EstimationResult(BaseModel):
    """Structured estimation with a server-derived cost total.

    The model proposes the phase breakdown, but ``total_cost_eur`` is always
    recomputed from it before field validation. This turns simple arithmetic
    errors into normalisation instead of costly Instructor retries.
    """

    summary: str = Field(min_length=10, max_length=1200)
    confidence_pct: int = Field(ge=0, le=100)
    phases: list[Phase] = Field(min_length=1, max_length=8)
    total_duration_weeks: int = Field(ge=1, le=104)
    total_cost_eur: int = Field(ge=0, le=2_000_000)

    @model_validator(mode="before")
    @classmethod
    def derive_total_cost_from_phases(cls, data: Any) -> Any:
        """Treat the LLM-provided total as display-only and derive the truth."""
        if not isinstance(data, dict) or not isinstance(data.get("phases"), list):
            return data
        try:
            total_cost_eur = sum(int(phase["cost_eur"]) for phase in data["phases"])
        except (KeyError, TypeError, ValueError):
            # Let normal field validation report malformed phase data.
            return data
        return {**data, "total_cost_eur": total_cost_eur}

    @model_validator(mode="after")
    def phases_sum_matches_total(self) -> "EstimationResult":
        """Defensive invariant for values built without the before validator."""
        phase_sum = sum(p.cost_eur for p in self.phases)
        if phase_sum != self.total_cost_eur:
            raise ValueError(
                f"phases sum ({phase_sum} EUR) does not match total_cost_eur "
                f"({self.total_cost_eur} EUR); adjust either the phases or the total"
            )
        return self

    @model_validator(mode="after")
    def low_confidence_requires_out_of_scope_prefix(self) -> "EstimationResult":
        if self.confidence_pct < LOW_CONFIDENCE_THRESHOLD and not self.summary.startswith(
            OUT_OF_SCOPE_PREFIX
        ):
            raise ValueError(
                f"confidence_pct < {LOW_CONFIDENCE_THRESHOLD} requires summary to "
                f"start with {OUT_OF_SCOPE_PREFIX!r}; refuse the estimation if the "
                f"description is too vague to size"
            )
        return self


class EstimationResponse(BaseModel):
    """Wraps the validated result, the prompt version that produced it, and
    whether it came from a cache (exact or semantic)."""

    result: EstimationResult
    prompt_version: str
    cached: bool = False


from app.schemas.acb import BossTrace  # noqa: E402


class ACBResponse(EstimationResponse):
    """Conversational response with the Actor-Critic-Boss audit trail.

    Same shape as ``EstimationResponse`` plus the ``acb`` field carrying the
    iteration log. The UI uses the trail to render an expander showing what
    the Critic flagged at each step and how the Boss decided.
    """

    acb: BossTrace
