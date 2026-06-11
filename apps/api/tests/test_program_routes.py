from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from autoresearch_api.db.errors import DataNotFoundError
from autoresearch_api.programs.router import (
    create_program,
    get_hypothesis,
    get_program,
    get_program_dag,
)
from autoresearch_api.programs.service import InvalidCursorError, ProgramService
from autoresearch_api.programs.spec import ProgramSpec

NOW = datetime.now(UTC)


class FakeConn:
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


class FakeDatabase(FakeConn):
    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[FakeConn]:
        yield self


@pytest.mark.asyncio
async def test_create_program_writes_program_budget_and_root() -> None:
    db = FakeDatabase()
    program_id = uuid4()
    root_id = uuid4()
    db.fetchrow_queue = [
        _program_row(program_id),
        _budget_row(program_id),
        _hypothesis_row(root_id, program_id, depth=0),
    ]
    spec = ProgramSpec(
        name="demo",
        goal="g",
        budget_usd=Decimal("10"),
        root_hypothesis="root idea",
    )

    response = await create_program(spec, ProgramService(db))

    assert response.id == program_id
    assert response.type == "literature_synthesis"
    assert response.budget.cap_usd == Decimal("10")
    assert response.root_hypothesis_id == root_id
    program_inserts = [call for call in db.calls if "insert into crucible.programs" in call[0]]
    assert program_inserts
    assert "demo" not in program_inserts[0][0]


@pytest.mark.asyncio
async def test_create_program_without_root_hypothesis_skips_node() -> None:
    db = FakeDatabase()
    program_id = uuid4()
    db.fetchrow_queue = [_program_row(program_id), _budget_row(program_id)]
    spec = ProgramSpec(name="demo", goal="g", budget_usd=Decimal("5"))

    response = await create_program(spec, ProgramService(db))

    assert response.root_hypothesis_id is None
    assert not any("insert into crucible.hypotheses" in call[0] for call in db.calls)


@pytest.mark.asyncio
async def test_get_program_returns_program_with_budget() -> None:
    db = FakeDatabase()
    program_id = uuid4()
    db.fetchrow_queue = [_program_row(program_id), _budget_row(program_id)]

    response = await get_program(program_id, ProgramService(db))

    assert response.id == program_id
    assert response.budget.cap_usd == Decimal("10")


@pytest.mark.asyncio
async def test_get_program_missing_raises_not_found() -> None:
    db = FakeDatabase()

    with pytest.raises(DataNotFoundError):
        await get_program(uuid4(), ProgramService(db))


@pytest.mark.asyncio
async def test_get_hypothesis_missing_raises_not_found() -> None:
    db = FakeDatabase()

    with pytest.raises(DataNotFoundError):
        await get_hypothesis(uuid4(), ProgramService(db))


@pytest.mark.asyncio
async def test_get_program_dag_returns_nodes_and_next_cursor() -> None:
    db = FakeDatabase()
    program_id = uuid4()
    db.fetchrow_queue = [_program_row(program_id)]
    db.fetch_result = [
        _hypothesis_row(uuid4(), program_id, depth=0),
        _hypothesis_row(uuid4(), program_id, depth=1),
    ]

    response = await get_program_dag(
        program_id, ProgramService(db), limit=1, cursor=None, root=None
    )

    assert len(response.nodes) == 1
    assert response.next_cursor is not None


@pytest.mark.asyncio
async def test_get_program_dag_with_bad_cursor_raises_invalid_cursor() -> None:
    db = FakeDatabase()
    program_id = uuid4()
    db.fetchrow_queue = [_program_row(program_id)]

    with pytest.raises(InvalidCursorError):
        await get_program_dag(
            program_id,
            ProgramService(db),
            limit=10,
            cursor="!!!not-base64!!!",
            root=None,
        )


def _program_row(program_id: UUID) -> dict[str, Any]:
    return {
        "id": program_id,
        "name": "demo",
        "type": "literature_synthesis",
        "version": "v1",
        "spec_yaml": "name: demo\n",
        "neo4j_graph_id": None,
        "owner": None,
        "created_at": NOW,
        "updated_at": NOW,
    }


def _budget_row(program_id: UUID) -> dict[str, Any]:
    return {
        "id": uuid4(),
        "program_id": program_id,
        "cap_usd": Decimal("10"),
        "spent_usd": Decimal("0"),
        "updated_at": NOW,
    }


def _hypothesis_row(hypothesis_id: UUID, program_id: UUID, *, depth: int) -> dict[str, Any]:
    return {
        "id": hypothesis_id,
        "program_id": program_id,
        "parent_id": None,
        "depth": depth,
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


def _compact(query: str) -> str:
    return " ".join(query.split())
