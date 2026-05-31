from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from autoresearch_api.db.artifacts import ArtifactKeys
from autoresearch_api.db.errors import DataNotFoundError
from autoresearch_api.db.repositories import (
    EventRepository,
    HypothesisRepository,
    ProgramRepository,
    Repositories,
)


class FakePostgres:
    def __init__(
        self,
        *,
        row: dict[str, Any] | None = None,
        rows: list[dict[str, Any]] | None = None,
    ):
        self.row = row
        self.rows = rows or []
        self.calls: list[tuple[str, str, tuple[object, ...]]] = []

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        self.calls.append(("fetchrow", _compact(query), args))
        return self.row

    async def fetch(self, query: str, *args: object) -> list[dict[str, Any]]:
        self.calls.append(("fetch", _compact(query), args))
        return self.rows

    async def execute(self, query: str, *args: object) -> str:
        self.calls.append(("execute", _compact(query), args))
        return "OK"


@pytest.mark.asyncio
async def test_program_create_uses_parameterized_insert() -> None:
    program_id = uuid4()
    created_at = datetime.now(UTC)
    db = FakePostgres(
        row={
            "id": program_id,
            "name": "nanochat",
            "version": "v1",
            "spec_yaml": "goal: improve evals",
            "neo4j_graph_id": None,
            "owner": "atlas",
            "created_at": created_at,
            "updated_at": created_at,
        },
    )

    program = await ProgramRepository(db).create(
        name="nanochat",
        spec_yaml="goal: improve evals",
        owner="atlas",
    )

    assert program.id == program_id
    assert program.name == "nanochat"
    _, query, args = db.calls[0]
    assert "insert into crucible.programs" in query
    assert "values ($1, $2, $3, $4, $5)" in query
    assert "nanochat" not in query
    assert args == ("nanochat", "v1", "goal: improve evals", None, "atlas")


@pytest.mark.asyncio
async def test_hypothesis_create_is_idempotent_on_named_constraint() -> None:
    program_id = uuid4()
    hypothesis_id = uuid4()
    created_at = datetime.now(UTC)
    db = FakePostgres(
        row={
            "id": hypothesis_id,
            "program_id": program_id,
            "parent_id": None,
            "depth": 0,
            "status": "proposed",
            "proposal_hash": "proposal-001",
            "patch_diff_ref": None,
            "compact_summary": "root idea",
            "lg_thread_id": None,
            "proposer_run_id": None,
            "neo4j_context_ref": None,
            "created_at": created_at,
            "updated_at": created_at,
        },
    )

    hypothesis = await HypothesisRepository(db).create_idempotent(
        program_id=program_id,
        parent_id=None,
        depth=0,
        proposal_hash="proposal-001",
        compact_summary="root idea",
    )

    assert hypothesis.id == hypothesis_id
    _, query, args = db.calls[0]
    assert "on conflict on constraint hypotheses_idempotency_key do nothing" in query
    assert "parent_id is not distinct from $2" in query
    assert "proposal-001" not in query
    assert args[:5] == (program_id, None, 0, "proposed", "proposal-001")


@pytest.mark.asyncio
async def test_program_get_raises_explicit_not_found_error() -> None:
    db = FakePostgres(row=None)

    with pytest.raises(DataNotFoundError):
        await ProgramRepository(db).get(uuid4())


@pytest.mark.asyncio
async def test_event_record_uses_partial_unique_stream_id_conflict() -> None:
    run_id = uuid4()
    event_id = uuid4()
    created_at = datetime.now(UTC)
    db = FakePostgres(
        row={
            "id": event_id,
            "run_id": run_id,
            "ts": created_at,
            "kind": "stdout",
            "payload": {"line": "done"},
            "redis_stream_id": "1710000000-0",
            "created_at": created_at,
        },
    )

    event = await EventRepository(db).record(
        run_id=run_id,
        kind="stdout",
        payload={"line": "done"},
        redis_stream_id="1710000000-0",
    )

    assert event.redis_stream_id == "1710000000-0"
    _, query, args = db.calls[0]
    assert "on conflict (run_id, redis_stream_id) where redis_stream_id is not null" in query
    assert args == (run_id, "stdout", {"line": "done"}, "1710000000-0")


def test_repository_facade_covers_sprint_one_tables() -> None:
    repos = Repositories.from_postgres(FakePostgres())

    assert repos.programs
    assert repos.hypotheses
    assert repos.runs
    assert repos.claims
    assert repos.approvals
    assert repos.budgets
    assert repos.events


def test_artifact_key_layout_matches_object_store_design() -> None:
    program_id = uuid4()
    hypothesis_id = uuid4()
    run_id = uuid4()
    claim_id = uuid4()

    assert (
        ArtifactKeys.patch_diff(program_id, hypothesis_id)
        == f"programs/{program_id}/hypotheses/{hypothesis_id}/patch.diff"
    )
    assert ArtifactKeys.run_prefix(program_id, run_id) == f"programs/{program_id}/runs/{run_id}/"
    assert (
        ArtifactKeys.run_event_log(program_id, run_id)
        == f"programs/{program_id}/runs/{run_id}/events.jsonl"
    )
    assert (
        ArtifactKeys.claim_source(program_id, claim_id, ".json")
        == f"programs/{program_id}/claims/{claim_id}/source.json"
    )


def _compact(query: str) -> str:
    return " ".join(query.split())
