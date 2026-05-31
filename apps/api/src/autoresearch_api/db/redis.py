from __future__ import annotations

from typing import Any
from uuid import UUID

from redis.asyncio import Redis

from autoresearch_api.settings import Settings


class RedisStreams:
    def __init__(self, client: Redis):
        self._client = client

    @classmethod
    def connect(cls, settings: Settings) -> RedisStreams:
        client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=settings.dependency_timeout_seconds,
            socket_timeout=settings.dependency_timeout_seconds,
            decode_responses=True,
        )
        return cls(client)

    async def close(self) -> None:
        await self._client.aclose()

    async def ping(self) -> bool:
        return bool(await self._client.ping())

    async def append_run_event(
        self,
        run_id: UUID,
        *,
        kind: str,
        payload: str,
        ts: str,
    ) -> str:
        stream_id = await self._client.xadd(
            f"run:{run_id}:events",
            {"kind": kind, "payload": payload, "ts": ts},
        )
        return str(stream_id)

    async def publish_program_trace(self, program_id: UUID, message: str) -> int:
        return int(await self._client.publish(f"program:{program_id}:traces", message))

    async def set_run_status(self, run_id: UUID, status: str) -> None:
        await self._client.set(f"run:{run_id}:status", status)

    async def read_run_events(
        self,
        run_id: UUID,
        *,
        start: str = "0-0",
        count: int = 100,
    ) -> list[dict[str, Any]]:
        rows = await self._client.xrange(f"run:{run_id}:events", min=start, count=count)
        return [{"id": stream_id, "fields": fields} for stream_id, fields in rows]
