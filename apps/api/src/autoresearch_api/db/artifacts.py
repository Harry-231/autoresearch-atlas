from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import boto3
from botocore.config import Config

from autoresearch_api.settings import Settings


@dataclass(frozen=True)
class ArtifactKeys:
    @staticmethod
    def patch_diff(program_id: UUID, hypothesis_id: UUID) -> str:
        return f"programs/{program_id}/hypotheses/{hypothesis_id}/patch.diff"

    @staticmethod
    def run_prefix(program_id: UUID, run_id: UUID) -> str:
        return f"programs/{program_id}/runs/{run_id}/"

    @staticmethod
    def run_event_log(program_id: UUID, run_id: UUID) -> str:
        return f"programs/{program_id}/runs/{run_id}/events.jsonl"

    @staticmethod
    def claim_source(program_id: UUID, claim_id: UUID, suffix: str) -> str:
        normalized_suffix = suffix.lstrip(".")
        return f"programs/{program_id}/claims/{claim_id}/source.{normalized_suffix}"


class ArtifactStore:
    def __init__(self, client: Any, bucket: str):
        self._client = client
        self._bucket = bucket

    @classmethod
    def connect(cls, settings: Settings) -> ArtifactStore:
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
        return cls(client, settings.s3_bucket)

    def verify_bucket(self) -> None:
        self._client.head_bucket(Bucket=self._bucket)

    def put_bytes(
        self,
        key: str,
        body: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> str:
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )
        return key

    def get_bytes(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()
