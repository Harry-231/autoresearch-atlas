import asyncio
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, TypedDict

import anyio
import asyncpg
import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends
from neo4j import AsyncGraphDatabase
from neo4j.exceptions import AuthError, Neo4jError, ServiceUnavailable
from redis.asyncio import Redis
from redis.exceptions import RedisError

from autoresearch_api.settings import Settings, get_settings

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
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    probes = {
        "postgres": await _run_probe("postgres", lambda: _probe_postgres(settings), settings),
        "neo4j": await _run_probe("neo4j", lambda: _probe_neo4j(settings), settings),
        "redis": await _run_probe("redis", lambda: _probe_redis(settings), settings),
        "s3": await _run_probe("s3", lambda: _probe_s3(settings), settings),
    }
    status = "ok" if all(result["ok"] for result in probes.values()) else "degraded"
    return {"status": status, "dependencies": probes}


async def _run_probe(
    name: str,
    probe: Callable[[], Awaitable[ProbeResult]],
    settings: Settings,
) -> ProbeResult:
    try:
        return await asyncio.wait_for(probe(), timeout=settings.dependency_timeout_seconds)
    except TimeoutError:
        return {"ok": False, "details": {"error": f"{name} probe timed out"}}


async def _probe_postgres(settings: Settings) -> ProbeResult:
    connection: asyncpg.Connection | None = None
    try:
        connection = await asyncpg.connect(settings.database_url)
        row = await connection.fetchrow(
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
            settings.postgres_schema,
            settings.langgraph_checkpoint_schema,
            sorted(REQUIRED_CRUCIBLE_TABLES),
        )
    except (asyncpg.PostgresError, OSError) as exc:
        return {"ok": False, "details": {"error": str(exc)}}
    finally:
        if connection is not None:
            await connection.close()

    found_tables = set(row["crucible_tables"])
    missing_tables = sorted(REQUIRED_CRUCIBLE_TABLES - found_tables)
    details = {
        "schema": settings.postgres_schema,
        "checkpoint_schema": settings.langgraph_checkpoint_schema,
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


async def _probe_neo4j(settings: Settings) -> ProbeResult:
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
        async with driver.session() as session:
            row = await (await session.run("RETURN 1 AS ok")).single()
    except (AuthError, ServiceUnavailable, Neo4jError, OSError) as exc:
        return {"ok": False, "details": {"error": str(exc)}}
    finally:
        await driver.close()

    return {"ok": row is not None and row["ok"] == 1, "details": {"uri": settings.neo4j_uri}}


async def _probe_redis(settings: Settings) -> ProbeResult:
    client = Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=settings.dependency_timeout_seconds,
        socket_timeout=settings.dependency_timeout_seconds,
    )
    try:
        pong = await client.ping()
    except (RedisError, OSError) as exc:
        return {"ok": False, "details": {"error": str(exc)}}
    finally:
        await client.aclose()

    return {"ok": bool(pong), "details": {"url": _redact_url(settings.redis_url)}}


async def _probe_s3(settings: Settings) -> ProbeResult:
    return await anyio.to_thread.run_sync(_probe_s3_sync, settings)


def _probe_s3_sync(settings: Settings) -> ProbeResult:
    config = Config(
        s3={"addressing_style": "path" if settings.s3_force_path_style else "virtual"},
        retries={"max_attempts": 1},
    )
    client = boto3.client(
        "s3",
        endpoint_url=str(settings.s3_endpoint_url),
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
        config=config,
    )
    try:
        client.head_bucket(Bucket=settings.s3_bucket)
    except (BotoCoreError, ClientError, OSError) as exc:
        return {"ok": False, "details": {"bucket": settings.s3_bucket, "error": str(exc)}}

    return {
        "ok": True,
        "details": {
            "bucket": settings.s3_bucket,
            "endpoint": str(settings.s3_endpoint_url),
        },
    }


def _redact_url(value: str) -> str:
    if "@" not in value:
        return value
    scheme, rest = value.split("://", 1)
    return f"{scheme}://<redacted>@{rest.split('@', 1)[1]}"
