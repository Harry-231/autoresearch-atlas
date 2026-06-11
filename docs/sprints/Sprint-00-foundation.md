# Sprint 0 — Foundation & Local Runtime

**Layer:** Ground · **Status:** `Done` · **Milestone:** Foundation

## Goal

Make the repository bootable and prove the selected datastore foundation, so every
later layer has a real system of record to build on.

## Why this is the bottom

Nothing works without the stores and a way to verify them. This sprint creates the
ground truth: schemas, services, health probes, and a validator that fails loudly if
the foundation drifts.

## Feature scope

- Supabase/Postgres schema foundation (`crucible` + `lg_checkpoints`).
- Neo4j Community schema foundation (constraints + indexes only).
- Redis and MinIO local services.
- FastAPI health service.
- Local and hosted environment templates.
- Offline database validator.

## Deliverables

- `supabase/config.toml`, `supabase/schemas/*.sql`, baseline migration.
- `schema/neo4j/*.cypher`.
- `docker-compose.yml` (Neo4j, Redis, MinIO, bucket init).
- `apps/api` health endpoints.
- `.env.example`, `.env.hosting.example`.
- `tools/validate_database_foundation.py`.

## Checklist

- [x] `crucible` schema: 8 tables, closure trigger, idempotency key, pgvector column.
- [x] RLS enabled on product tables; private grants; server-side access only.
- [x] `lg_checkpoints` schema boundary present and isolated.
- [x] Neo4j CE UNIQUE constraints + range/full-text indexes.
- [x] Docker Compose brings up Neo4j, Redis, MinIO, and initializes the bucket.
- [x] `GET /health` and `GET /health/dependencies` implemented.
- [x] Local + hosting env templates complete.
- [x] Offline validator covers schemas, extensions, RLS, grants, Neo4j, env, probes.

## Acceptance criteria

- [x] `python tools/validate_database_foundation.py` passes.
- [x] `uv lock --check --project apps/api` passes.
- [x] `uv run --project apps/api ruff check apps/api/src` passes.
- [x] `pnpm check-types` passes.
- [x] `GET /health` returns `{"status":"ok"}` when the API runs.
- [x] `GET /health/dependencies` reports each configured store explicitly.

## Definition of Done

Foundation validates offline and live; local Supabase + `infra:up` services start;
live SQL verifies schemas/extensions/RLS/grants and all 8 `crucible` tables; live
Neo4j/Redis/S3 and the dependency probe pass. **Met.**

## Follow-up carried forward (from REFINEMENT)

- [ ] Add the **`lite` profile** to `docker-compose.yml` (Apache AGE in Postgres,
      `LISTEN/NOTIFY`, local FS) behind `--profile lite`, sharing the same repo/MCP
      API. Hardened in [Sprint 10](./Sprint-10-launch-readiness.md). (R1.1)
