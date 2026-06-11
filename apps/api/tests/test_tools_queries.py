from __future__ import annotations

import pytest
from pydantic import ValidationError

from autoresearch_api.tools.queries import StructuredGraphQuery, compile_graph_query


def test_node_by_id_requires_node_id() -> None:
    with pytest.raises(ValidationError):
        StructuredGraphQuery(kind="node_by_id")


def test_claims_for_program_requires_program_id() -> None:
    with pytest.raises(ValidationError):
        StructuredGraphQuery(kind="claims_for_program")


def test_unknown_kind_is_rejected() -> None:
    with pytest.raises(ValidationError):
        StructuredGraphQuery(kind="drop_tables", node_id="x")


def test_unknown_relationship_is_rejected() -> None:
    with pytest.raises(ValidationError):
        StructuredGraphQuery(kind="neighbors", node_id="x", relationship="DELETE")


def test_limit_bounds_enforced() -> None:
    with pytest.raises(ValidationError):
        StructuredGraphQuery(kind="node_by_id", node_id="n1", limit=0)
    with pytest.raises(ValidationError):
        StructuredGraphQuery(kind="node_by_id", node_id="n1", limit=1000)


def test_compile_node_by_id_binds_param() -> None:
    cypher, params = compile_graph_query(StructuredGraphQuery(kind="node_by_id", node_id="n1"))
    assert "MATCH (n {id: $node_id})" in cypher
    assert params["node_id"] == "n1"
    assert "n1" not in cypher  # value is bound, not interpolated


def test_compile_neighbors_includes_relationship_param() -> None:
    cypher, params = compile_graph_query(
        StructuredGraphQuery(kind="neighbors", node_id="n1", relationship="SUPPORTS", limit=5)
    )
    assert "type(r) = $relationship" in cypher
    assert params == {"limit": 5, "node_id": "n1", "relationship": "SUPPORTS"}


def test_compile_claims_for_program() -> None:
    cypher, params = compile_graph_query(
        StructuredGraphQuery(kind="claims_for_program", program_id="p1")
    )
    assert "(c:Claim {program_id: $program_id})" in cypher
    assert params["program_id"] == "p1"
    assert "node_id" not in params
