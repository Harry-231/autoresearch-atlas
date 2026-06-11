from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from neo4j.exceptions import Neo4jError, ServiceUnavailable

from autoresearch_api.db.neo4j import Neo4jClient
from autoresearch_api.db.postgres import PostgresDatabase
from autoresearch_api.db.repositories import (
    ClaimRecord,
    HypothesisRecord,
    Repositories,
    RunRecord,
)
from autoresearch_api.tools.queries import StructuredGraphQuery, compile_graph_query

_GRAPH_ERRORS = (Neo4jError, ServiceUnavailable, OSError)


class ToolService:
    """The read-mostly tool boundary agents use for context and DAG reads.

    Holds the datastore handles; callers (MCP server, REST router) get results, never
    credentials or raw query languages. The same instance backs both surfaces, so the
    safety properties are proven once.
    """

    def __init__(self, db: PostgresDatabase, neo4j: Neo4jClient):
        self._repos = Repositories.from_postgres(db)
        self._neo4j = neo4j

    async def get_dag_node(self, hypothesis_id: UUID) -> dict[str, Any]:
        return _hypothesis_view(await self._repos.hypotheses.get(hypothesis_id))

    async def get_run_summary(self, run_id: UUID) -> dict[str, Any]:
        return _run_view(await self._repos.runs.get(run_id))

    async def search_claims(self, text: str, k: int = 10) -> dict[str, Any]:
        results = await self._repos.claims.search_lexical(text, limit=k)
        return {
            "mode": "lexical",
            "query": text,
            "results": [_claim_view(claim) for claim in results],
        }

    async def query_domain_graph(self, query: StructuredGraphQuery) -> dict[str, Any]:
        cypher, params = compile_graph_query(query)
        try:
            records = await self._neo4j.read(cypher, params)
        except _GRAPH_ERRORS as exc:
            return {"kind": query.kind, "degraded": True, "records": [], "error": str(exc)}
        return {"kind": query.kind, "degraded": False, "records": records}

    async def get_context_pack(self, hypothesis_id: UUID) -> dict[str, Any]:
        hypothesis = await self._repos.hypotheses.get(hypothesis_id)
        claims = await self._repos.claims.list_for_hypothesis(hypothesis_id, limit=20)

        degraded = False
        domain_claims: list[dict[str, Any]] = []
        cypher, params = compile_graph_query(
            StructuredGraphQuery(kind="claims_for_program", program_id=str(hypothesis.program_id))
        )
        try:
            domain_claims = await self._neo4j.read(cypher, params)
        except _GRAPH_ERRORS:
            degraded = True

        return {
            "hypothesis": _hypothesis_view(hypothesis),
            "claims": [_claim_view(claim) for claim in claims],
            "domain_claims": domain_claims,
            "degraded": degraded,
        }

    async def record_claim(
        self,
        *,
        hypothesis_id: UUID,
        statement: str,
        source_artifact_ref: str | None = None,
        proposed_confidence: float = 0.5,
    ) -> dict[str, Any]:
        """Stage a proposed claim. Writes to claim_staging — never to durable truth."""
        staged = await self._repos.claim_staging.stage(
            hypothesis_id=hypothesis_id,
            statement=statement,
            source_artifact_ref=source_artifact_ref,
            proposed_confidence=Decimal(str(proposed_confidence)),
        )
        return {
            "staged": True,
            "target": "crucible.claim_staging",
            "id": str(staged.id),
            "hypothesis_id": str(staged.hypothesis_id),
            "status": staged.status,
        }


def _hypothesis_view(record: HypothesisRecord) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "program_id": str(record.program_id),
        "parent_id": str(record.parent_id) if record.parent_id is not None else None,
        "depth": record.depth,
        "status": record.status,
        "compact_summary": record.compact_summary,
    }


def _run_view(record: RunRecord) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "hypothesis_id": str(record.hypothesis_id),
        "backend": record.backend,
        "status": record.status,
        "score_vector": record.score_vector_json,
        "critic_verdict": record.critic_verdict_json,
    }


def _claim_view(record: ClaimRecord) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "hypothesis_id": str(record.hypothesis_id),
        "statement": record.statement,
        "confidence": float(record.confidence),
    }
