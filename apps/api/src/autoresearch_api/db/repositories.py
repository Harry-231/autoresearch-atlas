from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg

from autoresearch_api.db.errors import DataConflictError, DataNotFoundError
from autoresearch_api.db.postgres import PostgresExecutor

DEFAULT_APPROVAL_TTL = timedelta(hours=24)
DEFAULT_CLAIM_CONFIDENCE = Decimal("0.5")


@dataclass(frozen=True)
class ProgramRecord:
    id: UUID
    name: str
    type: str
    version: str
    spec_yaml: str
    neo4j_graph_id: str | None
    owner: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class HypothesisRecord:
    id: UUID
    program_id: UUID
    parent_id: UUID | None
    depth: int
    status: str
    proposal_hash: str
    patch_diff_ref: str | None
    compact_summary: str
    lg_thread_id: str | None
    proposer_run_id: str | None
    neo4j_context_ref: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class RunRecord:
    id: UUID
    hypothesis_id: UUID
    backend: str
    status: str
    started_at: datetime | None
    ended_at: datetime | None
    score_vector_json: dict[str, Any]
    critic_verdict_json: dict[str, Any]
    artifacts_ref: str | None
    event_log_ref: str | None
    langsmith_trace_id: str | None
    neo4j_context_snapshot_ref: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ClaimRecord:
    id: UUID
    hypothesis_id: UUID
    run_id: UUID | None
    statement: str
    source_artifact_ref: str | None
    confidence: Decimal
    neo4j_claim_id: str | None
    created_at: datetime


@dataclass(frozen=True)
class ClaimStagingRecord:
    id: UUID
    hypothesis_id: UUID
    run_id: UUID | None
    statement: str
    source_artifact_ref: str | None
    proposed_confidence: Decimal
    status: str
    created_at: datetime


@dataclass(frozen=True)
class ApprovalRecord:
    id: UUID
    run_id: UUID
    kind: str
    status: str
    ttl: timedelta
    requested_at: datetime
    decided_at: datetime | None
    decided_by: str | None
    audit: dict[str, Any]


@dataclass(frozen=True)
class BudgetRecord:
    id: UUID
    program_id: UUID
    cap_usd: Decimal
    spent_usd: Decimal
    updated_at: datetime


@dataclass(frozen=True)
class EventRecord:
    id: UUID
    run_id: UUID
    ts: datetime
    kind: str
    payload: dict[str, Any]
    redis_stream_id: str | None
    created_at: datetime


class ProgramRepository:
    def __init__(self, db: PostgresExecutor):
        self._db = db

    async def create(
        self,
        *,
        name: str,
        spec_yaml: str,
        type: str = "literature_synthesis",
        version: str = "v1",
        neo4j_graph_id: str | None = None,
        owner: str | None = None,
    ) -> ProgramRecord:
        row = await self._db.fetchrow(
            """
            insert into crucible.programs (name, type, version, spec_yaml, neo4j_graph_id, owner)
            values ($1, $2, $3, $4, $5, $6)
            returning *
            """,
            name,
            type,
            version,
            spec_yaml,
            neo4j_graph_id,
            owner,
        )
        return _program(row)

    async def get(self, program_id: UUID) -> ProgramRecord:
        row = await self._db.fetchrow(
            """
            select *
            from crucible.programs
            where id = $1
            """,
            program_id,
        )
        if row is None:
            raise DataNotFoundError(f"Program {program_id} was not found.")
        return _program(row)

    async def list_recent(self, *, limit: int = 100) -> list[ProgramRecord]:
        rows = await self._db.fetch(
            """
            select *
            from crucible.programs
            order by created_at desc
            limit $1
            """,
            limit,
        )
        return [_program(row) for row in rows]


class HypothesisRepository:
    def __init__(self, db: PostgresExecutor):
        self._db = db

    async def create_idempotent(
        self,
        *,
        program_id: UUID,
        parent_id: UUID | None,
        depth: int,
        proposal_hash: str,
        status: str = "proposed",
        patch_diff_ref: str | None = None,
        compact_summary: str = "",
        lg_thread_id: str | None = None,
        proposer_run_id: str | None = None,
        neo4j_context_ref: str | None = None,
    ) -> HypothesisRecord:
        row = await self._db.fetchrow(
            """
            with inserted as (
              insert into crucible.hypotheses (
                program_id,
                parent_id,
                depth,
                status,
                proposal_hash,
                patch_diff_ref,
                compact_summary,
                lg_thread_id,
                proposer_run_id,
                neo4j_context_ref
              )
              values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
              on conflict on constraint hypotheses_idempotency_key do nothing
              returning *
            )
            select *
            from inserted
            union all
            select *
            from crucible.hypotheses
            where program_id = $1
              and parent_id is not distinct from $2
              and proposal_hash = $5
            limit 1
            """,
            program_id,
            parent_id,
            depth,
            status,
            proposal_hash,
            patch_diff_ref,
            compact_summary,
            lg_thread_id,
            proposer_run_id,
            neo4j_context_ref,
        )
        if row is None:
            raise DataConflictError("Hypothesis insert returned no row.")
        return _hypothesis(row)

    async def get(self, hypothesis_id: UUID) -> HypothesisRecord:
        row = await self._db.fetchrow(
            """
            select *
            from crucible.hypotheses
            where id = $1
            """,
            hypothesis_id,
        )
        if row is None:
            raise DataNotFoundError(f"Hypothesis {hypothesis_id} was not found.")
        return _hypothesis(row)

    async def closure_depth(self, ancestor_id: UUID, descendant_id: UUID) -> int | None:
        row = await self._db.fetchrow(
            """
            select depth
            from crucible.hypothesis_closure
            where ancestor_id = $1
              and descendant_id = $2
            """,
            ancestor_id,
            descendant_id,
        )
        return None if row is None else int(row["depth"])

    async def list_for_program(
        self,
        program_id: UUID,
        *,
        limit: int,
        after_created_at: datetime | None = None,
        after_id: UUID | None = None,
    ) -> list[HypothesisRecord]:
        """Page a program's DAG nodes by a stable (created_at, id) keyset.

        Uses the ``(program_id, parent_id, status, depth)`` covering index; never a
        recursive CTE.
        """
        rows = await self._db.fetch(
            """
            select *
            from crucible.hypotheses
            where program_id = $1
              and ($2::timestamptz is null or (created_at, id) > ($2, $3))
            order by created_at, id
            limit $4
            """,
            program_id,
            after_created_at,
            after_id,
            limit,
        )
        return [_hypothesis(row) for row in rows]

    async def list_subtree(
        self,
        program_id: UUID,
        root_id: UUID,
        *,
        limit: int,
        after_created_at: datetime | None = None,
        after_id: UUID | None = None,
    ) -> list[HypothesisRecord]:
        """Page the descendants of ``root_id`` via the closure table (O(depth), no CTE)."""
        rows = await self._db.fetch(
            """
            select h.*
            from crucible.hypotheses h
            join crucible.hypothesis_closure c on c.descendant_id = h.id
            where c.ancestor_id = $1
              and h.program_id = $2
              and ($3::timestamptz is null or (h.created_at, h.id) > ($3, $4))
            order by h.created_at, h.id
            limit $5
            """,
            root_id,
            program_id,
            after_created_at,
            after_id,
            limit,
        )
        return [_hypothesis(row) for row in rows]


class RunRepository:
    def __init__(self, db: PostgresExecutor):
        self._db = db

    async def create(
        self,
        *,
        hypothesis_id: UUID,
        backend: str,
        status: str = "queued",
        artifacts_ref: str | None = None,
    ) -> RunRecord:
        row = await self._db.fetchrow(
            """
            insert into crucible.runs (hypothesis_id, backend, status, artifacts_ref)
            values ($1, $2, $3, $4)
            returning *
            """,
            hypothesis_id,
            backend,
            status,
            artifacts_ref,
        )
        return _run(row)

    async def get(self, run_id: UUID) -> RunRecord:
        row = await self._db.fetchrow(
            """
            select *
            from crucible.runs
            where id = $1
            """,
            run_id,
        )
        if row is None:
            raise DataNotFoundError(f"Run {run_id} was not found.")
        return _run(row)


class ClaimRepository:
    def __init__(self, db: PostgresExecutor):
        self._db = db

    async def create(
        self,
        *,
        hypothesis_id: UUID,
        statement: str,
        run_id: UUID | None = None,
        source_artifact_ref: str | None = None,
        confidence: Decimal = DEFAULT_CLAIM_CONFIDENCE,
        neo4j_claim_id: str | None = None,
    ) -> ClaimRecord:
        row = await self._db.fetchrow(
            """
            insert into crucible.claims (
              hypothesis_id,
              run_id,
              statement,
              source_artifact_ref,
              confidence,
              neo4j_claim_id
            )
            values ($1, $2, $3, $4, $5, $6)
            returning id,
                      hypothesis_id,
                      run_id,
                      statement,
                      source_artifact_ref,
                      confidence,
                      neo4j_claim_id,
                      created_at
            """,
            hypothesis_id,
            run_id,
            statement,
            source_artifact_ref,
            confidence,
            neo4j_claim_id,
        )
        return _claim(row)

    async def get(self, claim_id: UUID) -> ClaimRecord:
        row = await self._db.fetchrow(
            """
            select id,
                   hypothesis_id,
                   run_id,
                   statement,
                   source_artifact_ref,
                   confidence,
                   neo4j_claim_id,
                   created_at
            from crucible.claims
            where id = $1
            """,
            claim_id,
        )
        if row is None:
            raise DataNotFoundError(f"Claim {claim_id} was not found.")
        return _claim(row)

    async def list_for_hypothesis(self, hypothesis_id: UUID, *, limit: int = 20) -> list[ClaimRecord]:
        rows = await self._db.fetch(
            """
            select id,
                   hypothesis_id,
                   run_id,
                   statement,
                   source_artifact_ref,
                   confidence,
                   neo4j_claim_id,
                   created_at
            from crucible.claims
            where hypothesis_id = $1
            order by created_at desc
            limit $2
            """,
            hypothesis_id,
            limit,
        )
        return [_claim(row) for row in rows]

    async def search_lexical(self, text: str, *, limit: int) -> list[ClaimRecord]:
        """Case-insensitive substring search over claim statements (parameterized).

        Placeholder ranking until Sprint 6 adds pgvector semantic recall. The value
        is bound as a parameter; no untrusted text is interpolated into SQL.
        """
        rows = await self._db.fetch(
            """
            select id,
                   hypothesis_id,
                   run_id,
                   statement,
                   source_artifact_ref,
                   confidence,
                   neo4j_claim_id,
                   created_at
            from crucible.claims
            where statement ilike '%' || $1 || '%'
            order by created_at desc
            limit $2
            """,
            text,
            limit,
        )
        return [_claim(row) for row in rows]


class ClaimStagingRepository:
    def __init__(self, db: PostgresExecutor):
        self._db = db

    async def stage(
        self,
        *,
        hypothesis_id: UUID,
        statement: str,
        run_id: UUID | None = None,
        source_artifact_ref: str | None = None,
        proposed_confidence: Decimal = DEFAULT_CLAIM_CONFIDENCE,
    ) -> ClaimStagingRecord:
        """Write a proposed claim to the staging area — never to durable truth."""
        row = await self._db.fetchrow(
            """
            insert into crucible.claim_staging (
              hypothesis_id,
              run_id,
              statement,
              source_artifact_ref,
              proposed_confidence
            )
            values ($1, $2, $3, $4, $5)
            returning *
            """,
            hypothesis_id,
            run_id,
            statement,
            source_artifact_ref,
            proposed_confidence,
        )
        return _claim_staging(row)

    async def list_for_hypothesis(
        self, hypothesis_id: UUID, *, limit: int = 50
    ) -> list[ClaimStagingRecord]:
        rows = await self._db.fetch(
            """
            select *
            from crucible.claim_staging
            where hypothesis_id = $1
            order by created_at desc
            limit $2
            """,
            hypothesis_id,
            limit,
        )
        return [_claim_staging(row) for row in rows]


class ApprovalRepository:
    def __init__(self, db: PostgresExecutor):
        self._db = db

    async def create(
        self,
        *,
        run_id: UUID,
        kind: str,
        ttl: timedelta = DEFAULT_APPROVAL_TTL,
        audit: dict[str, Any] | None = None,
    ) -> ApprovalRecord:
        row = await self._db.fetchrow(
            """
            insert into crucible.approvals (run_id, kind, ttl, audit)
            values ($1, $2, $3, $4)
            returning *
            """,
            run_id,
            kind,
            ttl,
            audit or {},
        )
        return _approval(row)

    async def get(self, approval_id: UUID) -> ApprovalRecord:
        row = await self._db.fetchrow(
            """
            select *
            from crucible.approvals
            where id = $1
            """,
            approval_id,
        )
        if row is None:
            raise DataNotFoundError(f"Approval {approval_id} was not found.")
        return _approval(row)


class BudgetRepository:
    def __init__(self, db: PostgresExecutor):
        self._db = db

    async def upsert(self, *, program_id: UUID, cap_usd: Decimal) -> BudgetRecord:
        row = await self._db.fetchrow(
            """
            insert into crucible.budgets (program_id, cap_usd)
            values ($1, $2)
            on conflict (program_id)
            do update set cap_usd = excluded.cap_usd,
                          updated_at = now()
            returning *
            """,
            program_id,
            cap_usd,
        )
        return _budget(row)

    async def get_for_program(self, program_id: UUID) -> BudgetRecord:
        row = await self._db.fetchrow(
            """
            select *
            from crucible.budgets
            where program_id = $1
            """,
            program_id,
        )
        if row is None:
            raise DataNotFoundError(f"Budget for program {program_id} was not found.")
        return _budget(row)


class EventRepository:
    def __init__(self, db: PostgresExecutor):
        self._db = db

    async def record(
        self,
        *,
        run_id: UUID,
        kind: str,
        payload: dict[str, Any],
        redis_stream_id: str | None = None,
    ) -> EventRecord:
        row = await self._db.fetchrow(
            """
            insert into crucible.events (run_id, kind, payload, redis_stream_id)
            values ($1, $2, $3, $4)
            on conflict (run_id, redis_stream_id) where redis_stream_id is not null
            do update set payload = excluded.payload
            returning *
            """,
            run_id,
            kind,
            payload,
            redis_stream_id,
        )
        return _event(row)

    async def list_for_run(self, run_id: UUID, *, limit: int = 100) -> list[EventRecord]:
        rows = await self._db.fetch(
            """
            select *
            from crucible.events
            where run_id = $1
            order by ts asc
            limit $2
            """,
            run_id,
            limit,
        )
        return [_event(row) for row in rows]


@dataclass(frozen=True)
class Repositories:
    programs: ProgramRepository
    hypotheses: HypothesisRepository
    runs: RunRepository
    claims: ClaimRepository
    claim_staging: ClaimStagingRepository
    approvals: ApprovalRepository
    budgets: BudgetRepository
    events: EventRepository

    @classmethod
    def from_postgres(cls, db: PostgresExecutor) -> Repositories:
        return cls(
            programs=ProgramRepository(db),
            hypotheses=HypothesisRepository(db),
            runs=RunRepository(db),
            claims=ClaimRepository(db),
            claim_staging=ClaimStagingRepository(db),
            approvals=ApprovalRepository(db),
            budgets=BudgetRepository(db),
            events=EventRepository(db),
        )


def _program(row: asyncpg.Record | dict[str, Any] | None) -> ProgramRecord:
    _require_row(row, "program")
    return ProgramRecord(
        id=row["id"],
        name=row["name"],
        type=row["type"],
        version=row["version"],
        spec_yaml=row["spec_yaml"],
        neo4j_graph_id=row["neo4j_graph_id"],
        owner=row["owner"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _hypothesis(row: asyncpg.Record | dict[str, Any] | None) -> HypothesisRecord:
    _require_row(row, "hypothesis")
    return HypothesisRecord(
        id=row["id"],
        program_id=row["program_id"],
        parent_id=row["parent_id"],
        depth=row["depth"],
        status=row["status"],
        proposal_hash=row["proposal_hash"],
        patch_diff_ref=row["patch_diff_ref"],
        compact_summary=row["compact_summary"],
        lg_thread_id=row["lg_thread_id"],
        proposer_run_id=row["proposer_run_id"],
        neo4j_context_ref=row["neo4j_context_ref"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _run(row: asyncpg.Record | dict[str, Any] | None) -> RunRecord:
    _require_row(row, "run")
    return RunRecord(
        id=row["id"],
        hypothesis_id=row["hypothesis_id"],
        backend=row["backend"],
        status=row["status"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        score_vector_json=row["score_vector_json"],
        critic_verdict_json=row["critic_verdict_json"],
        artifacts_ref=row["artifacts_ref"],
        event_log_ref=row["event_log_ref"],
        langsmith_trace_id=row["langsmith_trace_id"],
        neo4j_context_snapshot_ref=row["neo4j_context_snapshot_ref"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _claim(row: asyncpg.Record | dict[str, Any] | None) -> ClaimRecord:
    _require_row(row, "claim")
    return ClaimRecord(
        id=row["id"],
        hypothesis_id=row["hypothesis_id"],
        run_id=row["run_id"],
        statement=row["statement"],
        source_artifact_ref=row["source_artifact_ref"],
        confidence=row["confidence"],
        neo4j_claim_id=row["neo4j_claim_id"],
        created_at=row["created_at"],
    )


def _claim_staging(row: asyncpg.Record | dict[str, Any] | None) -> ClaimStagingRecord:
    _require_row(row, "claim_staging")
    return ClaimStagingRecord(
        id=row["id"],
        hypothesis_id=row["hypothesis_id"],
        run_id=row["run_id"],
        statement=row["statement"],
        source_artifact_ref=row["source_artifact_ref"],
        proposed_confidence=row["proposed_confidence"],
        status=row["status"],
        created_at=row["created_at"],
    )


def _approval(row: asyncpg.Record | dict[str, Any] | None) -> ApprovalRecord:
    _require_row(row, "approval")
    return ApprovalRecord(
        id=row["id"],
        run_id=row["run_id"],
        kind=row["kind"],
        status=row["status"],
        ttl=row["ttl"],
        requested_at=row["requested_at"],
        decided_at=row["decided_at"],
        decided_by=row["decided_by"],
        audit=row["audit"],
    )


def _budget(row: asyncpg.Record | dict[str, Any] | None) -> BudgetRecord:
    _require_row(row, "budget")
    return BudgetRecord(
        id=row["id"],
        program_id=row["program_id"],
        cap_usd=row["cap_usd"],
        spent_usd=row["spent_usd"],
        updated_at=row["updated_at"],
    )


def _event(row: asyncpg.Record | dict[str, Any] | None) -> EventRecord:
    _require_row(row, "event")
    return EventRecord(
        id=row["id"],
        run_id=row["run_id"],
        ts=row["ts"],
        kind=row["kind"],
        payload=row["payload"],
        redis_stream_id=row["redis_stream_id"],
        created_at=row["created_at"],
    )


def _require_row(row: asyncpg.Record | dict[str, Any] | None, label: str) -> None:
    if row is None:
        raise DataNotFoundError(f"Expected {label} row was not returned.")
