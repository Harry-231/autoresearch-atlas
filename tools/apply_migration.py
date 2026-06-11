"""Apply a SQL migration file directly to the configured Postgres.

A Supabase-CLI-free path to apply migrations (the CLI ships no win32-x64 binary).
Connects with the application's ``DATABASE_URL`` (read from the environment /
``.env`` via the app settings, falling back to the local default) and executes the
file as a single multi-statement script. Migrations are written to be idempotent,
so re-running is safe.

Usage:
    uv run --project apps/api python tools/apply_migration.py <path-to.sql>
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg

DEFAULT_DB_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"


def _database_url() -> str:
    try:
        from autoresearch_api.settings import get_settings

        return get_settings().database_url
    except Exception:  # noqa: BLE001 - settings import is best-effort; fall back to env
        return os.getenv("DATABASE_URL", DEFAULT_DB_URL)


async def _apply(path: Path, database_url: str) -> None:
    sql = path.read_text(encoding="utf-8")
    connection = await asyncpg.connect(dsn=database_url)
    try:
        await connection.execute(sql)
    finally:
        await connection.close()


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python tools/apply_migration.py <path-to.sql>", file=sys.stderr)
        return 2

    path = Path(args[0])
    if not path.exists():
        print(f"error: migration file not found: {path}", file=sys.stderr)
        return 2

    database_url = _database_url()
    try:
        asyncio.run(_apply(path, database_url))
    except (asyncpg.PostgresError, OSError) as exc:
        print(f"error: failed to apply {path}: {exc}", file=sys.stderr)
        return 1

    print(f"applied {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
