import pytest

from app.prompts.loader import render_estimation_prompt
from app.schemas.estimation import (
    DetailLevel,
    EstimationRequest,
    OutputFormat,
    ProjectType,
)


def _request(**overrides: object) -> EstimationRequest:
    values: dict[str, object] = {
        "description": "A platform for coordinating volunteer shifts and events.",
        "project_type": ProjectType.WEB_SAAS,
        "detail_level": DetailLevel.MEDIUM,
        "output_format": OutputFormat.PHASES_TABLE,
    }
    values.update(overrides)
    return EstimationRequest(**values)


def test_render_estimation_prompt_includes_user_and_examples() -> None:
    system, user = render_estimation_prompt(_request())

    assert "senior software estimation consultant" in system
    assert "phases_table" in system
    assert "warehouse inventory scanner" in system
    assert "<project_description>" in user
    assert "</project_description>" in user
    assert "volunteer shifts and events" in user


def test_render_estimation_prompt_applies_output_and_detail_branches() -> None:
    narrative_system, _ = render_estimation_prompt(
        _request(detail_level=DetailLevel.SUMMARY, output_format=OutputFormat.NARRATIVE)
    )

    phases_system, _ = render_estimation_prompt(
        _request(detail_level=DetailLevel.SUMMARY, output_format=OutputFormat.PHASES_TABLE)
    )
    assert "concise narrative" in narrative_system
    assert "phases_table" not in narrative_system
    assert "phases_table" in phases_system


def test_detailed_lists_assumptions_per_phase_but_summary_does_not() -> None:
    detailed_system, _ = render_estimation_prompt(_request(detail_level=DetailLevel.DETAILED))
    summary_system, _ = render_estimation_prompt(_request(detail_level=DetailLevel.SUMMARY))

    assert "list assumptions per phase" in detailed_system.lower()
    assert "list assumptions per phase" not in summary_system.lower()


def test_render_estimation_prompt_supports_version_parameter() -> None:
    system, user = render_estimation_prompt(_request(), version="v1")

    assert system and user

    with pytest.raises(ValueError, match="Unknown estimation prompt version"):
        render_estimation_prompt(_request(), version="v2")
