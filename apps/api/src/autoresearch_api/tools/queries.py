from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

GraphQueryKind = Literal["node_by_id", "neighbors", "claims_for_program"]
RelationshipType = Literal["USES", "EVALUATES_ON", "SUPPORTS", "CONTRADICTS", "DERIVES_FROM"]


class StructuredGraphQuery(BaseModel):
    """A parameterized, allow-listed domain-graph query.

    Agents and the UI choose a ``kind`` and supply parameters; they never send raw
    Cypher. Each kind maps to a fixed, bounded-depth template in ``_TEMPLATES``.
    """

    model_config = ConfigDict(extra="forbid")

    kind: GraphQueryKind
    node_id: str | None = None
    program_id: str | None = None
    relationship: RelationshipType | None = None
    limit: int = Field(default=25, ge=1, le=100)

    @model_validator(mode="after")
    def _require_params(self) -> StructuredGraphQuery:
        if self.kind in ("node_by_id", "neighbors") and not self.node_id:
            raise ValueError(f"{self.kind} requires node_id")
        if self.kind == "claims_for_program" and not self.program_id:
            raise ValueError("claims_for_program requires program_id")
        return self


# Fixed templates. The Cypher text is never built from input — only parameter
# *values* vary — and every traversal is single-hop (bounded depth).
_TEMPLATES: dict[str, str] = {
    "node_by_id": (
        "MATCH (n {id: $node_id}) "
        "RETURN labels(n) AS labels, n.id AS id, properties(n) AS properties "
        "LIMIT 1"
    ),
    "neighbors": (
        "MATCH (n {id: $node_id})-[r]-(m) "
        "WHERE $relationship IS NULL OR type(r) = $relationship "
        "RETURN type(r) AS relationship, labels(m) AS labels, m.id AS id "
        "LIMIT $limit"
    ),
    "claims_for_program": (
        "MATCH (c:Claim {program_id: $program_id}) "
        "RETURN c.id AS id, c.statement AS statement "
        "LIMIT $limit"
    ),
}


def compile_graph_query(query: StructuredGraphQuery) -> tuple[str, dict[str, object]]:
    """Return the fixed Cypher template and bound parameters for a structured query."""
    cypher = _TEMPLATES[query.kind]
    params: dict[str, object] = {"limit": query.limit}
    if query.node_id is not None:
        params["node_id"] = query.node_id
    if query.program_id is not None:
        params["program_id"] = query.program_id
    if query.kind == "neighbors":
        params["relationship"] = query.relationship
    return cypher, params
