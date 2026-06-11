# Sprint 1 — FastAPI Data-Access Layer

**Layer:** Server data plane · **Status:** `Done` · **Milestone:** Foundation

## Goal

Add typed, server-side access to the system of record without exposing database
clients to the frontend or to agents.

## Why now (bottom-up)

Every layer above must reach the DB through one safe, typed seam. Building the
repositories now means S2 (product API), S5 (graph nodes), and S6 (broker) all share
the same parameterized, pooled, error-mapped access — no scattered SQL later.

## Feature scope

- FastAPI settings hardening (`pydantic-settings`).
- Postgres connection-pool lifecycle.
- Repository modules for programs, hypotheses, runs, claims, budgets, approvals,
  events.
- Neo4j, Redis, and S3 client providers.
- Database error mapping to explicit API errors.

## Deliverables

- `apps/api/src/autoresearch_api/db/{postgres,repositories,neo4j,redis,artifacts,resources,errors}.py`
- `apps/api/src/autoresearch_api/dependencies.py`
- shared-resource health probes
- offline unit tests + gated live-DB tests

## Checklist

- [x] `Settings` loaded once via `@lru_cache get_settings()`; no scattered env reads.
- [x] Pool created/closed in app lifespan; no ad-hoc connections.
- [x] Frozen-dataclass read models for all core tables.
- [x] All SQL parameterized (`$1,$2,…`); no string interpolation.
- [x] Repositories for 8 core table families.
- [x] Neo4j/Redis/S3 provider wrappers.
- [x] Typed errors (`DataNotFoundError`, `DataConflictError`) mapped at boundaries.
- [x] Live-DB tests gated by `AUTORESEARCH_RUN_LIVE_DB_TESTS=1`.

## Acceptance criteria

- [x] API startup creates and closes pools cleanly.
- [x] Repository methods build no SQL from untrusted strings.
- [x] Program insert/read works against local Supabase.
- [x] Root and child hypothesis inserts populate `hypothesis_closure`.
- [x] Duplicate `(program_id, parent_id, proposal_hash)` write is idempotent or maps
      to a deterministic conflict result.

## Definition of Done

Offline repository/provider shape complete; live Supabase verifies program insert/
read, root/child closure rows, duplicate idempotency, and resource lifecycle/health.
**Met.**

## Notes

`docs/Sprint_*.md` execution reports are gitignored so local notes don't upload.
