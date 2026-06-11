from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Protocol

import asyncpg

from autoresearch_api.settings import Settings


class PostgresExecutor(Protocol):
    async def fetchrow(self, query: str, *args: object) -> asyncpg.Record | None: ...

    async def fetch(self, query: str, *args: object) -> Sequence[asyncpg.Record]: ...

    async def execute(self, query: str, *args: object) -> str: ...


class PostgresDatabase:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    @classmethod
    async def connect(cls, settings: Settings) -> PostgresDatabase:
        pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=settings.postgres_pool_min_size,
            max_size=settings.postgres_pool_max_size,
            command_timeout=settings.postgres_command_timeout_seconds,
        )
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def fetchrow(self, query: str, *args: object) -> asyncpg.Record | None:
        return await self._pool.fetchrow(query, *args)

    async def fetch(self, query: str, *args: object) -> Sequence[asyncpg.Record]:
        return await self._pool.fetch(query, *args)

    async def execute(self, query: str, *args: object) -> str:
        return await self._pool.execute(query, *args)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[PostgresExecutor]:
        """Yield a connection-bound executor wrapped in a single transaction.

        Use for multi-write flows that must be atomic (e.g. creating a program
        together with its budget and root hypothesis). The yielded object
        satisfies ``PostgresExecutor`` so repositories bind to it unchanged.
        """
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                yield connection
