from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_TABLES = [
    "programs",
    "hypotheses",
    "hypothesis_closure",
    "runs",
    "claims",
    "approvals",
    "budgets",
    "events",
]

REQUIRED_ENV_KEYS = [
    "DATABASE_URL",
    "POSTGRES_SCHEMA",
    "LANGGRAPH_CHECKPOINT_SCHEMA",
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "REDIS_URL",
    "S3_ENDPOINT_URL",
    "S3_ACCESS_KEY_ID",
    "S3_SECRET_ACCESS_KEY",
    "S3_BUCKET",
    "S3_REGION",
    "S3_FORCE_PATH_STYLE",
]


def main() -> int:
    failures: list[str] = []
    failures.extend(validate_supabase_sql())
    failures.extend(validate_neo4j())
    failures.extend(validate_env_examples())
    failures.extend(validate_api_scaffold())

    if failures:
        print("Database foundation validation failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Database foundation validation passed.")
    return 0


def validate_supabase_sql() -> list[str]:
    failures: list[str] = []
    schema_dir = ROOT / "supabase" / "schemas"
    migration_dir = ROOT / "supabase" / "migrations"
    expected_schema_files = [
        schema_dir / "00_extensions.sql",
        schema_dir / "01_crucible.sql",
        schema_dir / "02_security.sql",
    ]

    for path in expected_schema_files:
        if not path.exists():
            failures.append(f"missing Supabase schema file: {path.relative_to(ROOT)}")

    migration_files = sorted(migration_dir.glob("*_init_crucible.sql"))
    if len(migration_files) != 1:
        failures.append("expected exactly one *_init_crucible.sql migration")
        migration_text = ""
    else:
        migration_text = read(migration_files[0]).lower()

    combined = "\n".join(read(path) for path in expected_schema_files if path.exists()).lower()
    sql_texts = {"schema files": combined, "baseline migration": migration_text}

    for label, text in sql_texts.items():
        if "create extension if not exists vector" not in text:
            failures.append(f"{label} missing vector extension")
        if "create extension if not exists pgcrypto" not in text:
            failures.append(f"{label} missing pgcrypto extension")
        if "create schema if not exists crucible" not in text:
            failures.append(f"{label} missing crucible schema")
        if "create schema if not exists lg_checkpoints" not in text:
            failures.append(f"{label} missing lg_checkpoints schema")
        if "unique nulls not distinct" not in text:
            failures.append(f"{label} missing hypothesis idempotency key")
        if "create trigger hypotheses_insert_closure" not in text:
            failures.append(f"{label} missing closure trigger")
        if "embedding extensions.vector(1536)" not in text:
            failures.append(f"{label} missing 1536-dimension pgvector column")
        if "revoke all on schema crucible from anon" not in text:
            failures.append(f"{label} missing anon revoke for crucible schema")
        if "enable row level security" not in text:
            failures.append(f"{label} missing RLS enablement")

        for table in REQUIRED_TABLES:
            if f"create table crucible.{table}" not in text:
                failures.append(f"{label} missing table crucible.{table}")

    config = ROOT / "supabase" / "config.toml"
    if not config.exists():
        failures.append("missing supabase/config.toml")
    else:
        config_text = read(config)
        for schema_file in expected_schema_files:
            rel = f"./schemas/{schema_file.name}"
            if rel not in config_text:
                failures.append(f"supabase/config.toml missing schema path {rel}")

    return failures


def validate_neo4j() -> list[str]:
    failures: list[str] = []
    constraints = ROOT / "schema" / "neo4j" / "constraints.cypher"
    indexes = ROOT / "schema" / "neo4j" / "indexes.cypher"

    for path in [constraints, indexes]:
        if not path.exists():
            failures.append(f"missing Neo4j schema file: {path.relative_to(ROOT)}")

    text = "\n".join(read(path) for path in [constraints, indexes] if path.exists())
    upper = text.upper()
    if "NODE KEY" in upper:
        failures.append("Neo4j schema uses Enterprise-only NODE KEY")
    if re.search(r"REQUIRE\s+\w+\.\w+\s+IS\s+NOT\s+NULL", upper):
        failures.append("Neo4j schema uses Enterprise-only property existence constraint")

    for name in ["paper_id", "method_id", "entity_id", "claim_id", "hypothesis_seed_id"]:
        if name not in text:
            failures.append(f"Neo4j constraints missing {name}")

    for name in ["paper_doi", "method_name", "entity_name", "claim_program", "claim_fulltext"]:
        if name not in text:
            failures.append(f"Neo4j indexes missing {name}")

    return failures


def validate_env_examples() -> list[str]:
    failures: list[str] = []
    for path in [ROOT / ".env.example", ROOT / ".env.hosting.example"]:
        if not path.exists():
            failures.append(f"missing env example: {path.name}")
            continue
        text = read(path)
        for key in REQUIRED_ENV_KEYS:
            if f"{key}=" not in text:
                failures.append(f"{path.name} missing {key}")
    return failures


def validate_api_scaffold() -> list[str]:
    failures: list[str] = []
    required_paths = [
        ROOT / "apps" / "api" / "pyproject.toml",
        ROOT / "apps" / "api" / "package.json",
        ROOT / "apps" / "api" / "src" / "autoresearch_api" / "main.py",
        ROOT / "apps" / "api" / "src" / "autoresearch_api" / "settings.py",
        ROOT / "apps" / "api" / "src" / "autoresearch_api" / "health.py",
        ROOT / "apps" / "api" / "src" / "autoresearch_api" / "dependencies.py",
        ROOT / "apps" / "api" / "src" / "autoresearch_api" / "db" / "artifacts.py",
        ROOT / "apps" / "api" / "src" / "autoresearch_api" / "db" / "neo4j.py",
        ROOT / "apps" / "api" / "src" / "autoresearch_api" / "db" / "postgres.py",
        ROOT / "apps" / "api" / "src" / "autoresearch_api" / "db" / "redis.py",
        ROOT / "apps" / "api" / "src" / "autoresearch_api" / "db" / "repositories.py",
        ROOT / "apps" / "api" / "src" / "autoresearch_api" / "db" / "resources.py",
    ]
    for path in required_paths:
        if not path.exists():
            failures.append(f"missing API scaffold file: {path.relative_to(ROOT)}")

    expected_tokens = {
        ROOT / "apps" / "api" / "src" / "autoresearch_api" / "main.py": [
            "lifespan",
            "AppResources.create",
            "resources.close",
        ],
        ROOT / "apps" / "api" / "src" / "autoresearch_api" / "health.py": [
            "get_resources",
            "resources.postgres",
            "resources.neo4j",
            "resources.redis",
            "resources.artifacts",
        ],
        ROOT / "apps" / "api" / "src" / "autoresearch_api" / "db" / "postgres.py": [
            "asyncpg.create_pool",
            "min_size=settings.postgres_pool_min_size",
            "max_size=settings.postgres_pool_max_size",
        ],
        ROOT / "apps" / "api" / "src" / "autoresearch_api" / "db" / "neo4j.py": [
            "AsyncGraphDatabase.driver",
            "verify_connectivity",
            "RoutingControl",
        ],
        ROOT / "apps" / "api" / "src" / "autoresearch_api" / "db" / "redis.py": [
            "Redis.from_url",
            "xadd",
            "publish",
        ],
        ROOT / "apps" / "api" / "src" / "autoresearch_api" / "db" / "artifacts.py": [
            "boto3.client",
            "head_bucket",
            "put_object",
        ],
        ROOT / "apps" / "api" / "src" / "autoresearch_api" / "db" / "repositories.py": [
            "ProgramRepository",
            "HypothesisRepository",
            "RunRepository",
            "ClaimRepository",
            "ApprovalRepository",
            "BudgetRepository",
            "EventRepository",
            "on conflict on constraint hypotheses_idempotency_key",
        ],
    }

    for path, tokens in expected_tokens.items():
        if not path.exists():
            continue
        text = read(path)
        for token in tokens:
            if token not in text:
                failures.append(f"{path.relative_to(ROOT)} missing {token}")

    return failures


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
