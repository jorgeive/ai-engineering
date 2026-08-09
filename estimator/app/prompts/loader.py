"""Versioned Jinja prompt rendering for estimation requests."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.schemas.estimation import EstimationRequest

PROMPTS_ROOT = Path(__file__).parent


def render_estimation_prompt(
    request: EstimationRequest, version: str = "v1"
) -> tuple[str, str]:
    """Render the versioned system and user prompts for an estimation request."""
    version_root = PROMPTS_ROOT / "estimation" / version
    if not version_root.is_dir():
        raise ValueError(f"Unknown estimation prompt version: {version}")

    environment = Environment(
        loader=FileSystemLoader(str(PROMPTS_ROOT)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    context = {"request": request.model_dump(mode="json")}
    system = environment.get_template(f"estimation/{version}/system.j2").render(**context)
    user = environment.get_template(f"estimation/{version}/user.j2").render(**context)
    return system, user
