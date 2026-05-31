from __future__ import annotations

from dataclasses import dataclass

from autoresearch_api.db.artifacts import ArtifactStore
from autoresearch_api.db.neo4j import Neo4jClient
from autoresearch_api.db.postgres import PostgresDatabase
from autoresearch_api.db.redis import RedisStreams
from autoresearch_api.db.repositories import Repositories
from autoresearch_api.settings import Settings


@dataclass
class AppResources:
    settings: Settings
    postgres: PostgresDatabase
    repositories: Repositories
    neo4j: Neo4jClient
    redis: RedisStreams
    artifacts: ArtifactStore

    @classmethod
    async def create(cls, settings: Settings) -> AppResources:
        postgres = await PostgresDatabase.connect(settings)
        return cls(
            settings=settings,
            postgres=postgres,
            repositories=Repositories.from_postgres(postgres),
            neo4j=Neo4jClient.connect(settings),
            redis=RedisStreams.connect(settings),
            artifacts=ArtifactStore.connect(settings),
        )

    async def close(self) -> None:
        await self.redis.close()
        await self.neo4j.close()
        await self.postgres.close()
