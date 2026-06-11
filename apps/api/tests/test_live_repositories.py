from __future__ import annotations

import os
from collections.abc import AsyncIterator
from urllib.parse import urlparse
from uuid import uuid4

import pytest

from autoresearch_api.db.postgres import PostgresDatabase
from autoresearch_api.db.repositories import Repositories
from autoresearch_api.db.resources import AppResources
from autoresearch_api.health import dependency_health
from autoresearch_api.settings import Settings

pytestmark = pytest.mark.skipif(
    os.getenv("AUTORESEARCH_RUN_LIVE_DB_TESTS") != "1",
    reason="set AUTORESEARCH_RUN_LIVE_DB_TESTS=1 to run local Supabase integration tests",
)


@pytest.fixture
async def repositories() -> AsyncIterator[Repositories]:
    settings = _local_live_settings()
    postgres = await PostgresDatabase.connect(settings)
    try:
        yield Repositories.from_postgres(postgres)
    finally:
        await postgres.close()


@pytest.mark.asyncio
async def test_postgres_pool_lifecycle_against_local_supabase() -> None:
    postgres = await PostgresDatabase.connect(_local_live_settings())
    try:
        row = await postgres.fetchrow("select 1 as ok")
        assert row is not None
        assert row["ok"] == 1
    finally:
        await postgres.close()


@pytest.mark.asyncio
async def test_app_resources_lifecycle_and_dependency_health() -> None:
    resources = await AppResources.create(_local_live_settings())
    try:
        result = await dependency_health(resources)
        assert result["status"] == "ok"
        assert all(probe["ok"] for probe in result["dependencies"].values())
    finally:
        await resources.close()


@pytest.mark.asyncio
async def test_program_insert_read_against_local_supabase(repositories: Repositories) -> None:
    suffix = uuid4().hex

    created = await repositories.programs.create(
        name=f"sprint-1-live-{suffix}",
        spec_yaml=f"name: sprint-1-live-{suffix}\ngoal: verify program repository\n",
        owner="sprint-1-smoke",
    )
    fetched = await repositories.programs.get(created.id)

    assert fetched.id == created.id
    assert fetched.name == created.name
    assert fetched.spec_yaml == created.spec_yaml
    assert fetched.owner == "sprint-1-smoke"


@pytest.mark.asyncio
async def test_hypothesis_closure_and_idempotency_against_local_supabase(
    repositories: Repositories,
) -> None:
    suffix = uuid4().hex
    program = await repositories.programs.create(
        name=f"sprint-1-hypotheses-{suffix}",
        spec_yaml=f"name: sprint-1-hypotheses-{suffix}\ngoal: verify closure table\n",
        owner="sprint-1-smoke",
    )

    root = await repositories.hypotheses.create_idempotent(
        program_id=program.id,
        parent_id=None,
        depth=0,
        proposal_hash=f"root-{suffix}",
        compact_summary="Sprint 1 root smoke hypothesis.",
    )
    duplicate_root = await repositories.hypotheses.create_idempotent(
        program_id=program.id,
        parent_id=None,
        depth=0,
        proposal_hash=f"root-{suffix}",
        compact_summary="Sprint 1 root smoke hypothesis replay.",
    )

    child = await repositories.hypotheses.create_idempotent(
        program_id=program.id,
        parent_id=root.id,
        depth=1,
        proposal_hash=f"child-{suffix}",
        compact_summary="Sprint 1 child smoke hypothesis.",
    )
    duplicate_child = await repositories.hypotheses.create_idempotent(
        program_id=program.id,
        parent_id=root.id,
        depth=1,
        proposal_hash=f"child-{suffix}",
        compact_summary="Sprint 1 child smoke hypothesis replay.",
    )

    assert duplicate_root.id == root.id
    assert duplicate_child.id == child.id
    assert await repositories.hypotheses.closure_depth(root.id, root.id) == 0
    assert await repositories.hypotheses.closure_depth(child.id, child.id) == 0
    assert await repositories.hypotheses.closure_depth(root.id, child.id) == 1


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
