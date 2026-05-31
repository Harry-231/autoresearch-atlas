from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase, RoutingControl

from autoresearch_api.settings import Settings


class Neo4jClient:
    def __init__(self, driver: AsyncDriver):
        self._driver = driver

    @classmethod
    def connect(cls, settings: Settings) -> Neo4jClient:
        driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        return cls(driver)

    async def close(self) -> None:
        await self._driver.close()

    async def verify(self) -> None:
        await self._driver.verify_connectivity()

    async def read(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        result = await self._driver.execute_query(
            query,
            parameters_={**(parameters or {})},
            routing_=RoutingControl.READ,
        )
        return [record.data() for record in result.records]

    async def write(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> Sequence[dict[str, Any]]:
        result = await self._driver.execute_query(
            query,
            parameters_={**(parameters or {})},
            routing_=RoutingControl.WRITE,
        )
        return [record.data() for record in result.records]
