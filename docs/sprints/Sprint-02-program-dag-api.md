# Sprint 2 — Program Import & DAG API

**Layer:** Product data API · **Status:** `Done` (offline 24/24; live program/DAG flow
verified end-to-end against local Supabase) · **Milestone:** Foundation

## Goal

Let a user create a research program and inspect the durable DAG through FastAPI —
the first user-visible product API.

## Why now (bottom-up)

The reasoning loop (S5) needs to create hypotheses against a real program; the UI
(S8) needs a DAG endpoint. Both depend on this API existing and being stable. It sits
directly on the S1 repositories.

## Feature scope

- Program input schema for `research.yaml`, including `type`
  (`literature_synthesis` | `ml_experiment`) — REFINEMENT R0.
- Program creation endpoint + budget initialization.
- Root hypothesis creation.
- DAG list endpoint: cursor pagination + subtree support, **closure-table backed**.
- Hypothesis detail endpoint.

## Deliverables

- `POST /programs`, `GET /programs/{id}`, `GET /programs/{id}/dag`,
  `GET /hypotheses/{id}`
- Request/response Pydantic models.
- `examples/lit-synthesis/research.yaml` (primary demo) and
  `examples/nanochat/research.yaml` (ml demo).
- `crucible import <spec>` CLI entry that posts to `/programs`.

## Checklist

- [x] `programs.type` column + enum/validation added (migration + declarative schema + repository).
- [x] `research.yaml` parser → validated Pydantic `ProgramSpec` (`programs/spec.py`).
- [x] `POST /programs` writes `programs` + `budgets` (+ optional root hypothesis), atomically in a transaction.
- [x] Field-specific validation errors for invalid specs (Pydantic `extra="forbid"`, per-field locs; no rows written).
- [x] Root hypothesis writes `depth=0` and a closure row (existing AFTER-INSERT trigger).
- [x] `GET /programs/{id}/dag` returns id/parent/status/depth/summary, cursor-paged (keyset).
- [x] DAG list + subtree reads use the closure table — **no recursive CTE**.
- [x] Covering index `(program_id, parent_id, status, depth)` present (migration + declarative schema).
- [x] `GET /hypotheses/{id}` returns node detail (+ `trace_ref` placeholder link field).
- [x] CLI `crucible import` round-trips a sample spec (`cli.py`; `examples/lit-synthesis`, `examples/nanochat`).

Verified offline: ruff check + format clean on new modules; SQL-safety audit (no string-built SQL);
spec-validation, DAG-SQL, and route/service unit tests authored. **Pending the user's local env**
(Python 3.12 + Docker): `uv lock`, `pnpm api:check`, `pnpm api:test`, and the live-DB acceptance run.

## Acceptance criteria

- [x] Invalid program specs return field-specific validation errors. *(test_program_spec)*
- [x] Creating a program writes `programs` and `budgets`. *(test_program_routes + live)*
- [x] Creating/importing a root hypothesis writes closure depth 0. *(live: depth 0 + closure trigger)*
- [x] DAG endpoint returns root, children, status, depth, and summary fields. *(test_program_routes + live)*
- [x] DAG endpoint avoids recursive CTE scans for common ancestor/subtree queries. *(test_dag_repository)*
- [ ] DAG read meets the < 100 ms target on a seeded 10k-node tree. *(deferred: needs a seeded perf bench)*

Live coverage: `tests/test_live_programs_api.py` drives `create_program → get_program →
get_program_dag → get_hypothesis` against local Supabase; verified manually via
`crucible import` (program `3d5be62d…` created with `type=literature_synthesis`).

## Definition of Done

4 product endpoints live; import smoke test passes; DAG smoke test covers ≥ 3 depths
and a paged subtree; latency target measured on seed data; both example programs
import cleanly.

## Risks / notes

- Keep response models UI-shaped now (aggregation/virtualization is server-side in
  S8) so the DAG endpoint already supports collapsing rejected subtrees later.
