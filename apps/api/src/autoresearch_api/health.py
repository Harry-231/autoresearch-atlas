import asyncio
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, TypedDict

import anyio
import asyncpg
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends
from neo4j.exceptions import AuthError, Neo4jError, ServiceUnavailable
from redis.exceptions import RedisError

from autoresearch_api.db.resources import AppResources
from autoresearch_api.dependencies import get_resources

router = APIRouter(tags=["health"])

REQUIRED_CRUCIBLE_TABLES = {
    "programs",
    "hypotheses",
    "hypothesis_closure",
    "runs",
    "claims",
    "approvals",
    "budgets",
    "events",
}


class ProbeResult(TypedDict):
    ok: bool
    details: dict[str, Any]


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/dependencies")
async def dependency_health(
    resources: Annotated[AppResources, Depends(get_resources)],
) -> dict[str, Any]:
    probes = {
        "postgres": await _run_probe("postgres", lambda: _probe_postgres(resources), resources),
        "neo4j": await _run_probe("neo4j", lambda: _probe_neo4j(resources), resources),
        "redis": await _run_probe("redis", lambda: _probe_redis(resources), resources),
        "s3": await _run_probe("s3", lambda: _probe_s3(resources), resources),
    }
    status = "ok" if all(result["ok"] for result in probes.values()) else "degraded"
    return {"status": status, "dependencies": probes}


async def _run_probe(
    name: str,
    probe: Callable[[], Awaitable[ProbeResult]],
    resources: AppResources,
) -> ProbeResult:
    try:
        return await asyncio.wait_for(
            probe(),
            timeout=resources.settings.dependency_timeout_seconds,
        )
    except TimeoutError:
        return {"ok": False, "details": {"error": f"{name} probe timed out"}}


async def _probe_postgres(resources: AppResources) -> ProbeResult:
    try:
        row = await resources.postgres.fetchrow(
            """
            select
              exists (
                select 1 from information_schema.schemata where schema_name = $1
              ) as has_crucible_schema,
              exists (
                select 1 from information_schema.schemata where schema_name = $2
              ) as has_checkpoint_schema,
              exists (
                select 1 from pg_extension where extname = 'vector'
              ) as has_vector_extension,
              exists (
                select 1 from pg_extension where extname = 'pgcrypto'
              ) as has_pgcrypto_extension,
              (
                select coalesce(array_agg(table_name order by table_name), array[]::text[])
                from information_schema.tables
                where table_schema = $1
                  and table_name = any($3::text[])
              ) as crucible_tables
            """,
            resources.settings.postgres_schema,
            resources.settings.langgraph_checkpoint_schema,
            sorted(REQUIRED_CRUCIBLE_TABLES),
        )
    except (asyncpg.PostgresError, OSError) as exc:
        return {"ok": False, "details": {"error": str(exc)}}

    found_tables = set(row["crucible_tables"])
    missing_tables = sorted(REQUIRED_CRUCIBLE_TABLES - found_tables)
    details = {
        "schema": resources.settings.postgres_schema,
        "checkpoint_schema": resources.settings.langgraph_checkpoint_schema,
        "has_crucible_schema": row["has_crucible_schema"],
        "has_checkpoint_schema": row["has_checkpoint_schema"],
        "has_vector_extension": row["has_vector_extension"],
        "has_pgcrypto_extension": row["has_pgcrypto_extension"],
        "missing_tables": missing_tables,
    }
    ok = (
        details["has_crucible_schema"]
        and details["has_checkpoint_schema"]
        and details["has_vector_extension"]
        and details["has_pgcrypto_extension"]
        and not missing_tables
    )
    return {"ok": bool(ok), "details": details}


async def _probe_neo4j(resources: AppResources) -> ProbeResult:
    try:
        await resources.neo4j.verify()
    except (AuthError, ServiceUnavailable, Neo4jError, OSError) as exc:
        return {"ok": False, "details": {"error": str(exc)}}

    return {"ok": True, "details": {"uri": resources.settings.neo4j_uri}}


async def _probe_redis(resources: AppResources) -> ProbeResult:
    try:
        pong = await resources.redis.ping()
    except (RedisError, OSError) as exc:
        return {"ok": False, "details": {"error": str(exc)}}

    return {"ok": bool(pong), "details": {"url": _redact_url(resources.settings.redis_url)}}


async def _probe_s3(resources: AppResources) -> ProbeResult:
    return await anyio.to_thread.run_sync(_probe_s3_sync, resources)


def _probe_s3_sync(resources: AppResources) -> ProbeResult:
    try:
        resources.artifacts.verify_bucket()
    except (BotoCoreError, ClientError, OSError) as exc:
        return {
            "ok": False,
            "details": {"bucket": resources.settings.s3_bucket, "error": str(exc)},
        }

    return {
        "ok": True,
        "details": {
            "bucket": resources.settings.s3_bucket,
            "endpoint": str(resources.settings.s3_endpoint_url),
        },
    }


def _redact_url(value: str) -> str:
    if "@" not in value:
        return value
    scheme, rest = value.split("://", 1)
    return f"{scheme}://<redacted>@{rest.split('@', 1)[1]}"
