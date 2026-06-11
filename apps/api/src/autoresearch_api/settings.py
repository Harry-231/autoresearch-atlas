from functools import lru_cache
from typing import Annotated

from pydantic import AnyUrl, Field, PositiveFloat
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CORS_ALLOW_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    dependency_timeout_seconds: PositiveFloat = 3.0

    database_url: str = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
    postgres_schema: str = "crucible"
    langgraph_checkpoint_schema: str = "lg_checkpoints"
    postgres_pool_min_size: Annotated[int, Field(ge=0)] = 0
    postgres_pool_max_size: Annotated[int, Field(ge=1)] = 10
    postgres_command_timeout_seconds: PositiveFloat = 30.0

    neo4j_uri: str = "bolt://127.0.0.1:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "autoresearch"

    redis_url: str = "redis://127.0.0.1:6379/0"

    s3_endpoint_url: AnyUrl = Field(default="http://127.0.0.1:9000")
    s3_access_key_id: str = "minioadmin"
    s3_secret_access_key: str = "minioadmin"
    s3_bucket: str = "crucible-artifacts"
    s3_region: str = "us-east-1"
    s3_force_path_style: bool = True

    cors_allow_origins: list[str] = list(DEFAULT_CORS_ALLOW_ORIGINS)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
