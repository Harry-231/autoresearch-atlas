from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ProgramType = Literal["literature_synthesis", "ml_experiment"]


def _non_blank(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("must not be blank")
    return stripped


class BeamConfig(BaseModel):
    """Adaptive beam bounds (REFINEMENT R3.4). ``min``/``max`` are inclusive."""

    model_config = ConfigDict(extra="forbid")

    min: int = Field(default=1, ge=1)
    max: int = Field(default=4, ge=1)

    @model_validator(mode="after")
    def _min_le_max(self) -> BeamConfig:
        if self.min > self.max:
            raise ValueError("beam.min must be <= beam.max")
        return self


class ProgramSpec(BaseModel):
    """Validated form of a ``research.yaml`` program declaration.

    Field-specific validation errors surface through Pydantic, so an invalid spec
    posted to ``POST /programs`` yields a 422 with per-field locations and no rows
    are written.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    type: ProgramType = "literature_synthesis"
    goal: str
    version: str = "v1"
    owner: str | None = None
    metrics: list[str] = Field(default_factory=list)
    budget_usd: Decimal = Field(gt=0)
    beam: BeamConfig = Field(default_factory=BeamConfig)
    backend: str = "local"
    sources: list[str] = Field(default_factory=list)
    root_hypothesis: str | None = None

    @field_validator("name", "goal", "backend", "version")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        return _non_blank(value)

    @field_validator("metrics", "sources")
    @classmethod
    def _strip_list(cls, value: list[str]) -> list[str]:
        return [_non_blank(item) for item in value]

    @field_validator("owner", "root_hypothesis")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


def parse_research_yaml(text: str) -> ProgramSpec:
    """Parse and validate a ``research.yaml`` document into a :class:`ProgramSpec`."""
    data: Any = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("research.yaml must be a mapping of program fields")
    return ProgramSpec.model_validate(data)


def spec_to_yaml(spec: ProgramSpec) -> str:
    """Serialize a validated spec back to canonical YAML for durable storage."""
    payload = spec.model_dump(mode="json")
    return yaml.safe_dump(payload, sort_keys=True, default_flow_style=False)
