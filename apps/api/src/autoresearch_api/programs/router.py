from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel

from autoresearch_api.db.repositories import BudgetRecord, HypothesisRecord, ProgramRecord
from autoresearch_api.dependencies import get_program_service
from autoresearch_api.programs.service import DagPage, ProgramService, ProgramView
from autoresearch_api.programs.spec import ProgramSpec

router = APIRouter(tags=["programs"])

ServiceDep = Annotated[ProgramService, Depends(get_program_service)]


class BudgetResponse(BaseModel):
    cap_usd: Decimal
    spent_usd: Decimal


class ProgramResponse(BaseModel):
    id: UUID
    name: str
    type: str
    version: str
    owner: str | None
    created_at: datetime
    updated_at: datetime
    budget: BudgetResponse
    root_hypothesis_id: UUID | None = None


class ProgramSummary(BaseModel):
    id: UUID
    name: str
    type: str
    version: str
    owner: str | None
    created_at: datetime


class ProgramListResponse(BaseModel):
    programs: list[ProgramSummary]


class DagNode(BaseModel):
    id: UUID
    parent_id: UUID | None
    depth: int
    status: str
    compact_summary: str


class DagResponse(BaseModel):
    program_id: UUID
    nodes: list[DagNode]
    next_cursor: str | None


class HypothesisResponse(BaseModel):
    id: UUID
    program_id: UUID
    parent_id: UUID | None
    depth: int
    status: str
    compact_summary: str
    proposal_hash: str
    patch_diff_ref: str | None
    proposer_run_id: str | None
    neo4j_context_ref: str | None
    trace_ref: str | None
    created_at: datetime
    updated_at: datetime


@router.post("/programs", response_model=ProgramResponse, status_code=status.HTTP_201_CREATED)
async def create_program(spec: ProgramSpec, service: ServiceDep) -> ProgramResponse:
    view = await service.create_program(spec)
    return _program_response(view)


@router.get("/programs", response_model=ProgramListResponse)
async def list_programs(
    service: ServiceDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> ProgramListResponse:
    programs = await service.list_programs(limit=limit)
    return ProgramListResponse(programs=[_program_summary(program) for program in programs])


@router.get("/programs/{program_id}", response_model=ProgramResponse)
async def get_program(program_id: UUID, service: ServiceDep) -> ProgramResponse:
    view = await service.get_program(program_id)
    return _program_response(view)


@router.get("/programs/{program_id}/dag", response_model=DagResponse)
async def get_program_dag(
    program_id: UUID,
    service: ServiceDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    cursor: Annotated[str | None, Query()] = None,
    root: Annotated[UUID | None, Query(description="Return the subtree rooted here")] = None,
) -> DagResponse:
    page = await service.list_dag(program_id, limit=limit, cursor=cursor, root_id=root)
    return _dag_response(program_id, page)


@router.get("/hypotheses/{hypothesis_id}", response_model=HypothesisResponse)
async def get_hypothesis(hypothesis_id: UUID, service: ServiceDep) -> HypothesisResponse:
    record = await service.get_hypothesis(hypothesis_id)
    return _hypothesis_response(record)


def _program_response(view: ProgramView) -> ProgramResponse:
    return ProgramResponse(
        id=view.program.id,
        name=view.program.name,
        type=view.program.type,
        version=view.program.version,
        owner=view.program.owner,
        created_at=view.program.created_at,
        updated_at=view.program.updated_at,
        budget=_budget_response(view.budget),
        root_hypothesis_id=view.root.id if view.root is not None else None,
    )


def _budget_response(budget: BudgetRecord) -> BudgetResponse:
    return BudgetResponse(cap_usd=budget.cap_usd, spent_usd=budget.spent_usd)


def _program_summary(program: ProgramRecord) -> ProgramSummary:
    return ProgramSummary(
        id=program.id,
        name=program.name,
        type=program.type,
        version=program.version,
        owner=program.owner,
        created_at=program.created_at,
    )


def _dag_response(program_id: UUID, page: DagPage) -> DagResponse:
    return DagResponse(
        program_id=program_id,
        nodes=[_dag_node(node) for node in page.nodes],
        next_cursor=page.next_cursor,
    )


def _dag_node(record: HypothesisRecord) -> DagNode:
    return DagNode(
        id=record.id,
        parent_id=record.parent_id,
        depth=record.depth,
        status=record.status,
        compact_summary=record.compact_summary,
    )


def _hypothesis_response(record: HypothesisRecord) -> HypothesisResponse:
    return HypothesisResponse(
        id=record.id,
        program_id=record.program_id,
        parent_id=record.parent_id,
        depth=record.depth,
        status=record.status,
        compact_summary=record.compact_summary,
        proposal_hash=record.proposal_hash,
        patch_diff_ref=record.patch_diff_ref,
        proposer_run_id=record.proposer_run_id,
        neo4j_context_ref=record.neo4j_context_ref,
        trace_ref=record.proposer_run_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
