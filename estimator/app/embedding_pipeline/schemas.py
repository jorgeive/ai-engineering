"""Pydantic v2 contracts for normalized budget embedding."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Sector = Literal["finance", "ecommerce", "healthcare", "industrial"]
Complexity = Literal["low", "medium", "high"]
MetadataValue = str | int | float | bool


class PipelineModel(BaseModel):
    """Base model that rejects fields outside the embedding contract."""

    model_config = ConfigDict(extra="forbid")


class ClientMetadata(PipelineModel):
    """Client attributes that can be used to filter budget retrieval."""

    name: str = Field(min_length=1, max_length=200)
    sector: Sector
    country: str = Field(min_length=2, max_length=2, pattern=r"^[A-Z]{2}$")


class BudgetComponent(PipelineModel):
    """One estimated component from a normalized historical budget."""

    component_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=10_000)
    tech_stack: list[str] = Field(min_length=1, max_length=20)
    estimated_hours: int = Field(gt=0)
    complexity: Complexity
    dependencies: list[str] = Field(default_factory=list)


class Budget(PipelineModel):
    """A normalized budget and the components that make up its estimate."""

    budget_id: str = Field(min_length=1, max_length=128)
    client_metadata: ClientMetadata
    project_summary: str = Field(min_length=1, max_length=10_000)
    main_technology: str = Field(min_length=1, max_length=128)
    year: int = Field(ge=2000, le=2100)
    total_estimated_hours: int = Field(gt=0)
    components: list[BudgetComponent] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def components_match_budget_total(self) -> "Budget":
        """Reject malformed budgets before they reach the embedding pipeline."""

        component_ids = {component.component_id for component in self.components}
        if len(component_ids) != len(self.components):
            raise ValueError("component_id values must be unique within a budget")

        unknown_dependencies = {
            dependency
            for component in self.components
            for dependency in component.dependencies
            if dependency not in component_ids
        }
        if unknown_dependencies:
            raise ValueError(
                "component dependencies must refer to components in the same budget: "
                f"{sorted(unknown_dependencies)}"
            )

        component_hours = sum(component.estimated_hours for component in self.components)
        if component_hours != self.total_estimated_hours:
            raise ValueError(
                f"component hours ({component_hours}) must match total_estimated_hours "
                f"({self.total_estimated_hours})"
            )
        return self


class Chunk(PipelineModel):
    """A token-counted budget fragment ready for an embedding request."""

    chunk_id: str = Field(min_length=1, max_length=256)
    text: str = Field(min_length=1)
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)
    token_count: int = Field(ge=0)


class EmbeddedChunk(Chunk):
    """A chunk enriched with its vector representation."""

    embedding: list[float] = Field(min_length=1)


class IngestRequest(PipelineModel):
    """Payload accepted by the budget embedding ingestion endpoint."""

    budgets: list[Budget] = Field(min_length=1, max_length=10_000)


class IngestResponse(PipelineModel):
    """Chunks created by ingestion together with aggregate processing stats."""

    chunks: list[EmbeddedChunk]
    stats: dict[str, int | float]

    @model_validator(mode="after")
    def stats_have_required_values(self) -> "IngestResponse":
        required_stat_names = {
            "total_budgets",
            "total_chunks",
            "total_tokens",
            "estimated_cost_usd",
        }
        missing_stat_names = required_stat_names - self.stats.keys()
        if missing_stat_names:
            raise ValueError(f"stats is missing required values: {sorted(missing_stat_names)}")
        if any(self.stats[name] < 0 for name in required_stat_names):
            raise ValueError("stats values must be non-negative")
        return self
