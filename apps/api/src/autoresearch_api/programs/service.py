from __future__ import annotations

import base64
import binascii
import hashlib
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from autoresearch_api.db.postgres import PostgresDatabase
from autoresearch_api.db.repositories import (
    BudgetRecord,
    HypothesisRecord,
    ProgramRecord,
    Repositories,
)
from autoresearch_api.programs.spec import ProgramSpec, spec_to_yaml


class InvalidCursorError(ValueError):
    """Raised when a DAG pagination cursor cannot be decoded."""


@dataclass(frozen=True)
class ProgramView:
    program: ProgramRecord
    budget: BudgetRecord
    root: HypothesisRecord | None = None


@dataclass(frozen=True)
class DagPage:
    nodes: list[HypothesisRecord]
    next_cursor: str | None


class ProgramService:
    """Orchestrates program import and durable DAG reads on top of repositories."""

    def __init__(self, db: PostgresDatabase):
        self._db = db
        self._repos = Repositories.from_postgres(db)

    async def create_program(self, spec: ProgramSpec) -> ProgramView:
        """Atomically create the program, its budget, and an optional root node."""
        async with self._db.transaction() as connection:
            repos = Repositories.from_postgres(connection)
            program = await repos.programs.create(
                name=spec.name,
                type=spec.type,
                version=spec.version,
                spec_yaml=spec_to_yaml(spec),
                owner=spec.owner,
            )
            budget = await repos.budgets.upsert(program_id=program.id, cap_usd=spec.budget_usd)
            root: HypothesisRecord | None = None
            if spec.root_hypothesis is not None:
                root = await repos.hypotheses.create_idempotent(
                    program_id=program.id,
                    parent_id=None,
                    depth=0,
                    proposal_hash=_root_proposal_hash(spec.root_hypothesis),
                    compact_summary=spec.root_hypothesis,
                )
        return ProgramView(program=program, budget=budget, root=root)

    async def get_program(self, program_id: UUID) -> ProgramView:
        program = await self._repos.programs.get(program_id)
        budget = await self._repos.budgets.get_for_program(program.id)
        return ProgramView(program=program, budget=budget)

    async def list_programs(self, *, limit: int = 100) -> list[ProgramRecord]:
        return await self._repos.programs.list_recent(limit=limit)

    async def get_hypothesis(self, hypothesis_id: UUID) -> HypothesisRecord:
        return await self._repos.hypotheses.get(hypothesis_id)

    async def list_dag(
        self,
        program_id: UUID,
        *,
        limit: int,
        cursor: str | None = None,
        root_id: UUID | None = None,
    ) -> DagPage:
        # Surfaces a 404 for an unknown program before any DAG read.
        await self._repos.programs.get(program_id)

        after_created_at, after_id = _decode_cursor(cursor) if cursor else (None, None)
        fetch_limit = limit + 1  # over-fetch by one to detect a further page
        if root_id is not None:
            nodes = await self._repos.hypotheses.list_subtree(
                program_id,
                root_id,
                limit=fetch_limit,
                after_created_at=after_created_at,
                after_id=after_id,
            )
        else:
            nodes = await self._repos.hypotheses.list_for_program(
                program_id,
                limit=fetch_limit,
                after_created_at=after_created_at,
                after_id=after_id,
            )

        next_cursor: str | None = None
        if len(nodes) > limit:
            nodes = nodes[:limit]
            last = nodes[-1]
            next_cursor = _encode_cursor(last.created_at, last.id)
        return DagPage(nodes=nodes, next_cursor=next_cursor)


def _root_proposal_hash(statement: str) -> str:
    return "root-" + hashlib.sha256(statement.encode("utf-8")).hexdigest()[:32]


def _encode_cursor(created_at: datetime, node_id: UUID) -> str:
    raw = f"{created_at.isoformat()}|{node_id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        ts_str, id_str = raw.split("|", 1)
        return datetime.fromisoformat(ts_str), UUID(id_str)
    except (ValueError, binascii.Error) as exc:
        raise InvalidCursorError("malformed pagination cursor") from exc
