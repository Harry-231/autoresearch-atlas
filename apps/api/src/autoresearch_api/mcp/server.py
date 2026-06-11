from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from mcp.server.fastmcp import FastMCP

from autoresearch_api.db.neo4j import Neo4jClient
from autoresearch_api.db.postgres import PostgresDatabase
from autoresearch_api.settings import get_settings
from autoresearch_api.tools.queries import StructuredGraphQuery
from autoresearch_api.tools.service import ToolService

mcp = FastMCP("crucible-context")

_service: ToolService | None = None
_init_lock = asyncio.Lock()


async def _get_service() -> ToolService:
    """Lazily build a process-lifetime ToolService bound to the live datastores.

    The server holds the DB credentials; tool callers (agents) receive only results.
    """
    global _service
    if _service is None:
        async with _init_lock:
            if _service is None:
                settings = get_settings()
                postgres = await PostgresDatabase.connect(settings)
                neo4j = Neo4jClient.connect(settings)
                _service = ToolService(postgres, neo4j)
    return _service


@mcp.tool()
async def get_dag_node(hypothesis_id: str) -> dict[str, Any]:
    """Look up a hypothesis (DAG node) by id."""
    service = await _get_service()
    return await service.get_dag_node(UUID(hypothesis_id))


@mcp.tool()
async def get_run_summary(run_id: str) -> dict[str, Any]:
    """Look up an experiment run summary by id."""
    service = await _get_service()
    return await service.get_run_summary(UUID(run_id))


@mcp.tool()
async def search_claims(text: str, k: int = 10) -> dict[str, Any]:
    """Search claims by text (lexical until Sprint 6 adds semantic recall)."""
    service = await _get_service()
    return await service.search_claims(text, k)


@mcp.tool()
async def query_domain_graph(
    kind: str,
    node_id: str | None = None,
    program_id: str | None = None,
    relationship: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    """Run an allow-listed, bounded-depth domain-graph query (no raw Cypher)."""
    service = await _get_service()
    query = StructuredGraphQuery.model_validate(
        {
            "kind": kind,
            "node_id": node_id,
            "program_id": program_id,
            "relationship": relationship,
            "limit": limit,
        }
    )
    return await service.query_domain_graph(query)


@mcp.tool()
async def get_context_pack(hypothesis_id: str) -> dict[str, Any]:
    """Build a compact context pack for a hypothesis (flags degraded if Neo4j is down)."""
    service = await _get_service()
    return await service.get_context_pack(UUID(hypothesis_id))


@mcp.tool()
async def record_claim(
    hypothesis_id: str,
    statement: str,
    source_artifact_ref: str | None = None,
    proposed_confidence: float = 0.5,
) -> dict[str, Any]:
    """Stage a proposed claim (gated write — never writes durable truth)."""
    service = await _get_service()
    return await service.record_claim(
        hypothesis_id=UUID(hypothesis_id),
        statement=statement,
        source_artifact_ref=source_artifact_ref,
        proposed_confidence=proposed_confidence,
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
