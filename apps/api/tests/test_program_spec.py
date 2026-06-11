from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from autoresearch_api.programs.spec import ProgramSpec, parse_research_yaml, spec_to_yaml

VALID_YAML = """
name: demo
type: literature_synthesis
goal: synthesize evidence
budget_usd: 12.5
beam:
  min: 2
  max: 4
sources:
  - https://example.com/a
root_hypothesis: quantization preserves accuracy
"""


def test_parse_valid_research_yaml() -> None:
    spec = parse_research_yaml(VALID_YAML)
    assert spec.name == "demo"
    assert spec.type == "literature_synthesis"
    assert spec.budget_usd == Decimal("12.5")
    assert spec.beam.min == 2
    assert spec.beam.max == 4
    assert spec.backend == "local"


def test_defaults_are_applied() -> None:
    spec = ProgramSpec(name="x", goal="y", budget_usd=Decimal("1"))
    assert spec.type == "literature_synthesis"
    assert spec.version == "v1"
    assert spec.beam.min == 1
    assert spec.beam.max == 4
    assert spec.metrics == []
    assert spec.sources == []
    assert spec.root_hypothesis is None


def test_blank_name_is_field_error() -> None:
    with pytest.raises(ValidationError) as exc:
        ProgramSpec(name="   ", goal="y", budget_usd=Decimal("1"))
    assert any(error["loc"] == ("name",) for error in exc.value.errors())


def test_invalid_type_is_field_error() -> None:
    with pytest.raises(ValidationError) as exc:
        ProgramSpec(name="x", type="bogus", goal="y", budget_usd=Decimal("1"))
    assert any(error["loc"] == ("type",) for error in exc.value.errors())


def test_non_positive_budget_is_field_error() -> None:
    with pytest.raises(ValidationError) as exc:
        ProgramSpec(name="x", goal="y", budget_usd=Decimal("0"))
    assert any(error["loc"] == ("budget_usd",) for error in exc.value.errors())


def test_beam_min_greater_than_max_is_field_error() -> None:
    with pytest.raises(ValidationError) as exc:
        ProgramSpec(name="x", goal="y", budget_usd=Decimal("1"), beam={"min": 5, "max": 2})
    assert any(error["loc"] == ("beam",) for error in exc.value.errors())


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        ProgramSpec(name="x", goal="y", budget_usd=Decimal("1"), bogus=1)
    assert any(error["loc"] == ("bogus",) for error in exc.value.errors())


def test_non_mapping_yaml_is_rejected() -> None:
    with pytest.raises(ValueError, match="mapping"):
        parse_research_yaml("- just\n- a\n- list\n")


def test_spec_to_yaml_round_trips() -> None:
    spec = ProgramSpec(name="x", goal="y", budget_usd=Decimal("3.5"))
    reparsed = parse_research_yaml(spec_to_yaml(spec))
    assert reparsed.name == "x"
    assert reparsed.budget_usd == Decimal("3.5")
