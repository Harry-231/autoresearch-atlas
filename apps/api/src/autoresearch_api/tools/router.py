from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from autoresearch_api.dependencies import get_tool_service
from autoresearch_api.tools.queries import StructuredGraphQuery
from autoresearch_api.tools.service import ToolService

router = APIRouter(prefix="/tools", tags=["tools"])

ToolDep = Annotated[ToolService, Depends(get_tool_service)]


class RecordClaimRequest(BaseModel):
    hypothesis_id: UUID
    statement: str = Field(min_length=1)
    source_artifact_ref: str | None = None
    proposed_confidence: float = Field(default=0.5, ge=0, le=1)


@router.get("/dag-node/{hypothesis_id}")
async def dag_node(hypothesis_id: UUID, service: ToolDep) -> dict[str, Any]:
    return await service.get_dag_node(hypothesis_id)


@router.get("/run-summary/{run_id}")
async def run_summary(run_id: UUID, service: ToolDep) -> dict[str, Any]:
    return await service.get_run_summary(run_id)


@router.get("/search-claims")
async def search_claims(
    service: ToolDep,
    text: Annotated[str, Query(min_length=1)],
    k: Annotated[int, Query(ge=1, le=50)] = 10,
) -> dict[str, Any]:
    return await service.search_claims(text, k)


@router.post("/query-domain-graph")
async def query_domain_graph(query: StructuredGraphQuery, service: ToolDep) -> dict[str, Any]:
    return await service.query_domain_graph(query)


@router.get("/context-pack/{hypothesis_id}")
async def context_pack(hypothesis_id: UUID, service: ToolDep) -> dict[str, Any]:
    return await service.get_context_pack(hypothesis_id)


@router.post("/record-claim")
async def record_claim(request: RecordClaimRequest, service: ToolDep) -> dict[str, Any]:
    return await service.record_claim(
        hypothesis_id=request.hypothesis_id,
        statement=request.statement,
        source_artifact_ref=request.source_artifact_ref,
        proposed_confidence=request.proposed_confidence,
    )
