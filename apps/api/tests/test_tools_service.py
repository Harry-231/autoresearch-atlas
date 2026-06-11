from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from neo4j.exceptions import ServiceUnavailable

from autoresearch_api.db.errors import DataNotFoundError
from autoresearch_api.tools.queries import StructuredGraphQuery
from autoresearch_api.tools.service import ToolService

NOW = datetime.now(UTC)


class FakePostgres:
    def __init__(self) -> None:
        self.fetchrow_queue: list[dict[str, Any]] = []
        self.fetch_result: list[dict[str, Any]] = []
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        self.calls.append((_compact(query), args))
        return self.fetchrow_queue.pop(0) if self.fetchrow_queue else None

    async def fetch(self, query: str, *args: object) -> list[dict[str, Any]]:
        self.calls.append((_compact(query), args))
        return self.fetch_result

    async def execute(self, query: str, *args: object) -> str:
        self.calls.append((_compact(query), args))
        return "OK"


class FakeNeo4j:
    def __init__(
        self,
        *,
        records: list[dict[str, Any]] | None = None,
        error: Exception | None = None,
    ):
        self.records = records or []
        self.error = error
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    async def read(
        self, query: str, parameters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        self.calls.append((query, parameters))
        if self.error is not None:
            raise self.error
        return self.records


@pytest.mark.asyncio
async def test_search_claims_is_lexical_and_parameterized() -> None:
    db = FakePostgres()
    db.fetch_result = [_claim_row(uuid4(), "transformers scale well")]
    service = ToolService(db, FakeNeo4j())

    result = await service.search_claims("transformer", 5)

    assert result["mode"] == "lexical"
    assert result["query"] == "transformer"
    assert len(result["results"]) == 1
    query, args = db.calls[0]
    assert "ilike '%' || $1 || '%'" in query
    assert args == ("transformer", 5)
    assert "transformer" not in query


@pytest.mark.asyncio
async def test_query_domain_graph_degraded_when_neo4j_down() -> None:
    service = ToolService(FakePostgres(), FakeNeo4j(error=ServiceUnavailable("down")))

    result = await service.query_domain_graph(StructuredGraphQuery(kind="node_by_id", node_id="n1"))

    assert result["degraded"] is True
    assert result["records"] == []


@pytest.mark.asyncio
async def test_query_domain_graph_uses_bound_template() -> None:
    neo4j = FakeNeo4j(records=[{"id": "n1"}])
    service = ToolService(FakePostgres(), neo4j)

    result = await service.query_domain_graph(
        StructuredGraphQuery(kind="neighbors", node_id="n1", limit=10)
    )

    assert result["degraded"] is False
    assert result["records"] == [{"id": "n1"}]
    cypher, params = neo4j.calls[0]
    assert "$node_id" in cypher
    assert "n1" not in cypher
    assert params is not None
    assert params["node_id"] == "n1"


@pytest.mark.asyncio
async def test_get_context_pack_flags_degraded_when_graph_down() -> None:
    db = FakePostgres()
    hypothesis_id = uuid4()
    db.fetchrow_queue = [_hypothesis_row(hypothesis_id, uuid4())]
    db.fetch_result = []  # no claims for the hypothesis
    service = ToolService(db, FakeNeo4j(error=ServiceUnavailable("down")))

    pack = await service.get_context_pack(hypothesis_id)

    assert pack["degraded"] is True
    assert pack["hypothesis"]["id"] == str(hypothesis_id)
    assert pack["domain_claims"] == []


@pytest.mark.asyncio
async def test_record_claim_writes_to_staging_only() -> None:
    db = FakePostgres()
    hypothesis_id = uuid4()
    db.fetchrow_queue = [_staging_row(uuid4(), hypothesis_id)]
    service = ToolService(db, FakeNeo4j())

    result = await service.record_claim(hypothesis_id=hypothesis_id, statement="a proposed claim")

    assert result["staged"] is True
    assert result["target"] == "crucible.claim_staging"
    assert any("insert into crucible.claim_staging" in call[0] for call in db.calls)
    assert not any("insert into crucible.claims " in call[0] for call in db.calls)


@pytest.mark.asyncio
async def test_get_dag_node_missing_raises_not_found() -> None:
    service = ToolService(FakePostgres(), FakeNeo4j())

    with pytest.raises(DataNotFoundError):
        await service.get_dag_node(uuid4())


def _compact(query: str) -> str:
    return " ".join(query.split())


def _claim_row(claim_id: UUID, statement: str) -> dict[str, Any]:
    return {
        "id": claim_id,
        "hypothesis_id": uuid4(),
        "run_id": None,
        "statement": statement,
        "source_artifact_ref": None,
        "confidence": Decimal("0.5"),
        "neo4j_claim_id": None,
        "created_at": NOW,
    }


def _hypothesis_row(hypothesis_id: UUID, program_id: UUID) -> dict[str, Any]:
    return {
        "id": hypothesis_id,
        "program_id": program_id,
        "parent_id": None,
        "depth": 0,
        "status": "proposed",
        "proposal_hash": "hash",
        "patch_diff_ref": None,
        "compact_summary": "summary",
        "lg_thread_id": None,
        "proposer_run_id": None,
        "neo4j_context_ref": None,
        "created_at": NOW,
        "updated_at": NOW,
    }


def _staging_row(staging_id: UUID, hypothesis_id: UUID) -> dict[str, Any]:
    return {
        "id": staging_id,
        "hypothesis_id": hypothesis_id,
        "run_id": None,
        "statement": "a proposed claim",
        "source_artifact_ref": None,
        "proposed_confidence": Decimal("0.5"),
        "status": "staged",
        "created_at": NOW,
    }
