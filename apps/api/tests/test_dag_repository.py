from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from autoresearch_api.db.repositories import HypothesisRepository


class FakePostgres:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        self.calls.append((_compact(query), args))
        return self.rows[0] if self.rows else None

    async def fetch(self, query: str, *args: object) -> list[dict[str, Any]]:
        self.calls.append((_compact(query), args))
        return self.rows

    async def execute(self, query: str, *args: object) -> str:
        self.calls.append((_compact(query), args))
        return "OK"


@pytest.mark.asyncio
async def test_list_for_program_is_keyset_paged_without_recursion() -> None:
    db = FakePostgres(rows=[])
    program_id = uuid4()

    await HypothesisRepository(db).list_for_program(program_id, limit=50)

    query, args = db.calls[0]
    assert "from crucible.hypotheses" in query
    assert "with recursive" not in query
    assert "(created_at, id) >" in query
    assert "order by created_at, id" in query
    assert args == (program_id, None, None, 50)


@pytest.mark.asyncio
async def test_list_subtree_uses_closure_join_not_recursion() -> None:
    db = FakePostgres(rows=[])
    program_id = uuid4()
    root_id = uuid4()
    after_ts = datetime(2026, 1, 1, tzinfo=UTC)
    after_id = uuid4()

    await HypothesisRepository(db).list_subtree(
        program_id,
        root_id,
        limit=10,
        after_created_at=after_ts,
        after_id=after_id,
    )

    query, args = db.calls[0]
    assert "join crucible.hypothesis_closure" in query
    assert "c.ancestor_id = $1" in query
    assert "with recursive" not in query
    assert args == (root_id, program_id, after_ts, after_id, 10)


def _compact(query: str) -> str:
    return " ".join(query.split())
