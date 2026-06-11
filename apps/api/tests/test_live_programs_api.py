from __future__ import annotations

import os
from collections.abc import AsyncIterator
from decimal import Decimal
from urllib.parse import urlparse
from uuid import uuid4

import pytest

from autoresearch_api.db.postgres import PostgresDatabase
from autoresearch_api.programs.router import (
    create_program,
    get_hypothesis,
    get_program,
    get_program_dag,
)
from autoresearch_api.programs.service import ProgramService
from autoresearch_api.programs.spec import ProgramSpec
from autoresearch_api.settings import Settings

pytestmark = pytest.mark.skipif(
    os.getenv("AUTORESEARCH_RUN_LIVE_DB_TESTS") != "1",
    reason="set AUTORESEARCH_RUN_LIVE_DB_TESTS=1 to run local Supabase integration tests",
)


@pytest.fixture
async def service() -> AsyncIterator[ProgramService]:
    settings = _local_live_settings()
    postgres = await PostgresDatabase.connect(settings)
    try:
        yield ProgramService(postgres)
    finally:
        await postgres.close()


@pytest.mark.asyncio
async def test_program_and_dag_api_end_to_end(service: ProgramService) -> None:
    suffix = uuid4().hex
    spec = ProgramSpec(
        name=f"sprint-2-live-{suffix}",
        goal="verify program import and DAG API end to end",
        budget_usd=Decimal("12.5"),
        root_hypothesis="root idea for the sprint 2 live test",
    )

    created = await create_program(spec, service)
    assert created.type == "literature_synthesis"
    assert created.budget.cap_usd == Decimal("12.5")
    assert created.root_hypothesis_id is not None

    fetched = await get_program(created.id, service)
    assert fetched.id == created.id
    assert fetched.budget.cap_usd == created.budget.cap_usd

    dag = await get_program_dag(created.id, service, limit=50, cursor=None, root=None)
    root_nodes = [node for node in dag.nodes if node.id == created.root_hypothesis_id]
    assert len(root_nodes) == 1
    assert root_nodes[0].depth == 0

    hypothesis = await get_hypothesis(created.root_hypothesis_id, service)
    assert hypothesis.program_id == created.id
    assert hypothesis.depth == 0
    assert hypothesis.parent_id is None


def _local_live_settings() -> Settings:
    settings = Settings()
    if _is_local_database_url(settings.database_url):
        return settings
    if os.getenv("AUTORESEARCH_ALLOW_NONLOCAL_LIVE_DB_TESTS") == "1":
        return settings
    pytest.skip(
        "DATABASE_URL is not local; set AUTORESEARCH_ALLOW_NONLOCAL_LIVE_DB_TESTS=1 "
        "only when intentionally testing a non-local database"
    )


def _is_local_database_url(database_url: str) -> bool:
    parsed = urlparse(database_url)
    return parsed.hostname in {"127.0.0.1", "localhost", "::1"}
