# Autoresearch Atlas Sprint Plan

## How To Use This Plan

Each sprint is a feature set, not just a time box. Mark a sprint complete only
when its acceptance criteria pass in the repo. If a sprint needs to split, keep
the acceptance criteria stable and move unfinished scope to the next sprint.

Suggested cadence: one sprint is one to two weeks for a small team. The early
sprints should stay backend-heavy because the UI depends on stable program,
hypothesis, run, trace, and approval APIs.

## Progress Scale

Use this status vocabulary in project tracking:

- `Not Started` - no committed implementation.
- `In Progress` - implementation exists but acceptance criteria do not pass.
- `Blocked` - external dependency or unresolved design decision prevents work.
- `Done` - acceptance criteria pass locally; once CI exists, they also pass in
  CI.

## Sprint 0 - Foundation And Local Runtime

Status: `Done`

Goal: Make the repository bootable and prove the selected datastore foundation.

Feature set:

- Supabase/Postgres schema foundation.
- Neo4j Community schema foundation.
- Redis and MinIO local services.
- FastAPI health service.
- Local and hosted environment templates.
- Offline database validator.

Deliverables:

- `supabase/config.toml`
- `supabase/schemas/*.sql`
- baseline Supabase migration
- `schema/neo4j/*.cypher`
- `docker-compose.yml`
- `apps/api` health endpoints
- `.env.example`
- `.env.hosting.example`
- `tools/validate_database_foundation.py`
- local ignored execution report at `docs/Sprint_0.md`

Acceptance criteria:

- `python tools/validate_database_foundation.py` passes.
- `uv lock --check --project apps/api` passes.
- `uv run --project apps/api ruff check apps/api/src` passes.
- `pnpm check-types` passes.
- `GET /health` returns `{"status":"ok"}` when the API runs.
- `GET /health/dependencies` reports each configured store explicitly.

Progress metrics:

- Required schema objects present: 100 percent.
- API dependency probes implemented: 4 of 4.
- Local service config present: 4 of 4 stores.

Current notes:

- Offline validation, uv lock check, API source lint, monorepo type checks, and
  FastAPI health endpoint verification pass.
- Docker Desktop is installed and the local Supabase stack starts with
  `pnpm db:supabase:start`.
- Neo4j, Redis, MinIO, and bucket initialization start with `pnpm infra:up`.
- Live Supabase SQL verifies schemas, extensions, RLS, private grants, and all
  8 `crucible` tables.
- Live Neo4j constraints/indexes, Redis stream write/read, S3 object
  write/read, and `GET /health/dependencies` all pass.

## Sprint 1 - FastAPI Data Access Layer

Status: `Done`

Goal: Add typed server-side access to the system of record without exposing
database clients to the frontend or agents.

Feature set:

- FastAPI settings hardening.
- Postgres connection pool lifecycle.
- Repository modules for programs, hypotheses, runs, claims, budgets, approvals,
  and events.
- Neo4j, Redis, and S3 client providers.
- Database error mapping to explicit API errors.

Deliverables:

- `apps/api/src/autoresearch_api/db/postgres.py`
- `apps/api/src/autoresearch_api/db/repositories.py`
- `apps/api/src/autoresearch_api/db/neo4j.py`
- `apps/api/src/autoresearch_api/db/redis.py`
- `apps/api/src/autoresearch_api/db/artifacts.py`
- `apps/api/src/autoresearch_api/db/resources.py`
- `apps/api/src/autoresearch_api/dependencies.py`
- shared-resource health probes
- focused unit tests for repository behavior where live DB is not required
- local ignored execution report at `docs/Sprint_1.md`

Acceptance criteria:

- API startup creates and closes connection pools cleanly.
- Repository methods do not build SQL from untrusted strings.
- Program insert/read works against local Supabase.
- Root and child hypothesis inserts populate `hypothesis_closure`.
- Duplicate `(program_id, parent_id, proposal_hash)` write is idempotent or
  maps to a deterministic conflict result.

Progress metrics:

- Repository coverage for core tables: 8 of 8 implemented.
- Offline repository test cases: 6 passing.
- Live DB smoke cases passing: 4 of 4.

Current notes:

- Offline implementation is complete for repository/provider shape.
- Live Supabase repository verification passes for program insert/read,
  root/child closure rows, duplicate proposal idempotency, and shared resource
  lifecycle/dependency health.
- `api:test:live` is gated by `AUTORESEARCH_RUN_LIVE_DB_TESTS=1` so normal test
  runs do not require local Docker services.
- Sprint report files matching `docs/Sprint_*.md` are ignored so local execution
  notes do not upload to GitHub.

## Sprint 2 - Program Import And DAG API

Status: `Not Started`

Goal: Let users create a research program and inspect the durable DAG through
FastAPI.

Feature set:

- Program input schema for `research.yaml`.
- Program creation endpoint.
- Root hypothesis creation.
- DAG list endpoint with pagination and subtree support.
- Hypothesis detail endpoint.
- Budget initialization.

Deliverables:

- `POST /programs`
- `GET /programs/{id}`
- `GET /programs/{id}/dag`
- `GET /hypotheses/{id}`
- request and response Pydantic models
- sample `examples/nanochat/research.yaml`

Acceptance criteria:

- Invalid program specs return field-specific validation errors.
- Creating a program writes `programs` and `budgets`.
- Creating or importing a root hypothesis writes closure depth 0.
- DAG endpoint can return root, children, status, depth, and summary fields.
- DAG endpoint avoids recursive CTE scans for common ancestor/subtree queries.

Progress metrics:

- Product API endpoints delivered: 4 of 4.
- Program import smoke test passes.
- DAG smoke test covers at least 3 depths.

## Sprint 3 - MCP Tool Server

Status: `Not Started`

Goal: Build the safe tool boundary that agents use for context and DAG reads.

Feature set:

- MCP server process.
- Parameterized DAG and run lookup tools.
- pgvector claim search tool.
- Structured Neo4j query templates.
- Staged claim write tool.
- Tool schemas and negative tests for unsafe input.

Deliverables:

- `apps/mcp-server` or `apps/api/src/autoresearch_api/mcp`
- `get_context_pack(hypothesis_id)`
- `search_claims(text, k)`
- `query_domain_graph(structured_query)`
- `get_dag_node(id)`
- `get_run_summary(id)`
- `record_claim(...)` staging path

Acceptance criteria:

- No tool accepts raw SQL or raw Cypher from model input.
- MCP server holds credentials; agents receive no connection strings.
- `get_context_pack` returns `degraded=true` if Neo4j is unavailable.
- Claim search returns ranked pgvector results when embeddings exist.
- Tool tests include invalid ids, unsafe query payloads, and unavailable Neo4j.

Progress metrics:

- MCP tools delivered: 6 of 6.
- Unsafe raw-query paths: 0.
- Degradation test cases: Neo4j down, no embeddings, missing hypothesis.

## Sprint 4 - Local Execution Backend And Event Streaming

Status: `Not Started`

Goal: Dispatch local experiment jobs and persist live trace events for replay.

Feature set:

- Backend protocol.
- LocalBackend implementation.
- Run lifecycle state transitions.
- Redis stream producer.
- Event persister from Redis to Postgres.
- Artifact writer to MinIO/S3.

Deliverables:

- `apps/api/src/autoresearch_api/backends/base.py`
- `apps/api/src/autoresearch_api/backends/local.py`
- `POST /runs`
- `GET /runs/{id}`
- `GET /programs/{id}/stream`
- event persister worker
- artifact store service

Acceptance criteria:

- Submitting a local job creates a `runs` row.
- Run events are written to `run:{run_id}:events`.
- SSE stream receives live events for a program.
- Persister writes Redis events into `crucible.events`.
- Artifact refs follow the documented object-key layout.
- Redis loss after flush does not lose replayable events.

Progress metrics:

- Run lifecycle states covered: queued, running, succeeded, failed.
- Event path coverage: produce, stream, persist, replay-read.
- Artifact write/read smoke cases: patch, run prefix, event log.

## Sprint 5 - LangGraph Research Loop MVP

Status: `Not Started`

Goal: Add the first executable reasoning loop using ids in graph state and
durable writes for research truth.

Feature set:

- `langgraph.json`.
- ProgramState definition.
- Research loop graph.
- Proposer subgraph with structured proposal output.
- Evaluator node.
- Postgres checkpointer configured for `lg_checkpoints`.
- LocalBackend integration.

Deliverables:

- `apps/agent` or `crucible/graph`
- `research_loop`
- `proposer`
- `state`
- graph invocation script or CLI command
- integration test using the nanochat example

Acceptance criteria:

- Graph state stores ids and counters, not full research artifacts.
- Durable hypothesis/run writes occur before graph-node completion.
- Restart after checkpoint can resume without duplicating hypotheses.
- Proposer output is schema-validated.
- One local demo program can create at least one child hypothesis and run.

Progress metrics:

- Graph nodes delivered: select frontier, expand, run experiment, evaluate,
  persist.
- Resume/idempotency test cases: interrupted run, duplicate proposal replay.

## Sprint 6 - Context Broker And Domain Memory

Status: `Not Started`

Goal: Ingest sources and run outputs into the hybrid context engine.

Feature set:

- Paper ingestion job.
- Entity and method extraction.
- Claim extraction.
- Embedding generation.
- Neo4j graph writes.
- pgvector claim search.
- Context pack generation.

Deliverables:

- Context Broker worker.
- Ingestion queue or command.
- Neo4j write repository.
- Claim embedding service.
- context-pack service.

Acceptance criteria:

- Ingesting a sample paper creates Paper, Method, Entity, and Claim nodes.
- Extracted claims mirror into Postgres `claims`.
- Embeddings are stored for semantic recall.
- `get_context_pack` includes relevant claims, contradictions, prior run
  summaries, and degradation state.
- Neo4j unavailable path still returns pgvector-only context.

Progress metrics:

- Domain node types covered: 5 of 5.
- Relationship types covered: 5 of 5.
- Context-pack latency target measured on seed data.

## Sprint 7 - Critic, Approvals, Budgets, And Replay

Status: `Not Started`

Goal: Add the trust and governance loop around autonomous execution.

Feature set:

- Critic subgraph on separate model config.
- Multi-metric evaluator.
- Budget spend tracking.
- Approval records and decisions.
- LangGraph interrupt/resume integration.
- Replay endpoint.

Deliverables:

- critic subgraph
- evaluator service
- `GET /approvals?status=pending`
- `POST /approvals/{id}/decide`
- `POST /runs/{id}/replay`
- budget update service
- approval sweeper for TTL expiry

Acceptance criteria:

- Critic returns structured verdicts.
- Evaluator maps verdicts to keep, reject, quarantine, or escalate.
- Over-budget or risky work creates pending approval rows.
- Approval decisions resume parked graph runs.
- TTL expiry auto-denies and records audit state.
- Replay uses immutable artifact and event refs.

Progress metrics:

- Governance decisions covered: approve, deny, expire.
- Evaluator states covered: keep, reject, quarantine, escalate.
- Replay smoke test passes for one kept run.

## Sprint 8 - Product UI MVP

Status: `Not Started`

Goal: Build the first usable product surface for program progress and trust.

Feature set:

- Program list/detail.
- DAG visualization.
- Hypothesis detail.
- Run detail.
- Live trace panel.
- Approval queue.
- Replay action.

Deliverables:

- Next.js routes for programs, hypotheses, runs, and approvals.
- API client package or typed fetch helpers.
- DAG endpoint integration.
- SSE trace integration.
- Approval decision UI.

Acceptance criteria:

- User can create or select a program and inspect its DAG.
- DAG view supports collapsed or paged large trees.
- Hypothesis detail links to run, claims, artifacts, and traces.
- Approval queue can approve or deny pending requests.
- Live trace panel updates during local runs.
- UI never uses server-only secrets or database connection strings.

Progress metrics:

- Core screens delivered: program, DAG, hypothesis, run, approvals.
- User flows passing: inspect DAG, watch run, decide approval, replay run.

## Sprint 9 - Observability, Evals, And CI

Status: `Not Started`

Goal: Make quality, cost, and regressions measurable before launch.

Feature set:

- GitHub Actions CI.
- Schema validation in CI.
- API lint/type/compile checks.
- Frontend type checks.
- LangSmith tracing config.
- Critic reliability eval dataset.
- Proposer quality eval dataset.
- Demo cost guard.

Deliverables:

- `.github/workflows/ci.yml`
- LangSmith env docs.
- eval harness.
- nanochat regression demo.
- cost summary output.

Acceptance criteria:

- CI runs on pull requests and `main`.
- CI fails on schema drift or unsafe Neo4j schema additions.
- CI checks pnpm and uv workspaces.
- LangSmith trace ids are persisted on runs.
- Cost guard reports token and spend estimates for the demo.

Progress metrics:

- Required CI jobs passing: install, typecheck, lint, schema validate, API check.
- Eval datasets created: critic reliability, proposer quality, cost regression.

## Sprint 10 - Launch Readiness

Status: `Not Started`

Goal: Package the project for external contributors and self-hosted use.

Feature set:

- Contributor guide.
- Local quickstart.
- Hosted deployment guide.
- Migration and backup guide.
- Demo program docs.
- Security review.
- Release checklist.

Deliverables:

- `CONTRIBUTING.md`
- `docs/local_development.md`
- `docs/hosting.md`
- `docs/operations.md`
- `examples/nanochat/README.md`
- release checklist

Acceptance criteria:

- New contributor can run the local stack from a clean clone.
- Hosted setup explains Supabase, Neo4j, Redis, and S3 env values.
- Backup/restore guidance covers Postgres, Neo4j, and object storage.
- Security checklist covers secrets, RLS, MCP boundaries, and approval gates.
- Demo program can be run end-to-end by following docs.

Progress metrics:

- Docs walkthroughs verified from clean clone: local, hosted, demo.
- Release blockers open: 0.

## Cross-Sprint Backlog

These items should be pulled into the sprint where they become necessary:

- Auth model for single-tenant local use.
- Determinism mode policy for replay-critical programs.
- Modal backend.
- Colab backend.
- UI virtualization strategy for large DAGs.
- More formal migration tooling for versioned Neo4j changes.
- Dedicated extraction model evaluation.
- LangSmith self-hosting or managed configuration decision.

## Milestone Map

| Milestone | Sprints | Outcome |
| --- | --- | --- |
| Foundation | 0-2 | Local system of record and program/DAG API are usable |
| Agent MVP | 3-5 | Agents can read context, propose hypotheses, and run local experiments |
| Trust Loop | 6-7 | Context, critic, approvals, budgets, and replay are functional |
| Product MVP | 8 | Users can inspect and operate programs from the web UI |
| Launch | 9-10 | CI, evals, docs, and release process are ready |

## Current Recommended Next Sprint

Start Sprint 2 next: Program Import And DAG API.
