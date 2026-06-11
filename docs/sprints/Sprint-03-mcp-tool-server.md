# Sprint 3 — MCP Tool Server (+ Docker DBs + Test UI)

**Layer:** Agent data boundary · **Status:** `In Progress` · **Milestone:** Agent MVP
**Refined 2026-06-09.** Adds two pragmatic scope items on top of the original plan:
a **Docker-hosted Postgres** (so local dev needs no Supabase CLI) and a **thin shadcn
test UI** so the features built through Sprint 3 are clickable and verifiable.

## Goal

Build the safe tool boundary agents use for context and DAG reads — so the reasoning
loop (Sprint 5) never touches credentials or raw query languages — and make it
**testable now** via a REST mirror + a small web UI.

## Why this is the right next layer (bottom-up)

Sprint 5's agents must read data through tools, not the DB. Standing up the tool
boundary (and its safety invariants) before the loop makes secret-isolation
structural, not bolted on. The tools read Sprint 2's program/DAG data today;
context/claim tools return `degraded`/`lexical` results until Sprint 6 fills the
domain graph — by design.

## Refinements folded in

- **One tool logic core, two surfaces.** `ToolService` holds the parameterized,
  read-mostly logic. It is exposed as **MCP tools** (the agent boundary, the real
  Sprint 3 artifact) *and* as a **REST `/tools/*` mirror** (so the UI and humans can
  exercise the exact same logic). The UI calls FastAPI only — never the MCP server
  or the DB directly (System Design invariant).
- **Docker Postgres (REFINEMENT R1.1 down-payment).** `pgvector/pgvector:pg16` on
  `:54322` joins neo4j/redis/minio in `docker-compose.yml`, initialized from the
  declarative schema — the whole stack is now `pnpm db:up`, no Supabase CLI. (The
  Supabase CLI ships no win32-x64 binary; this unblocks Windows entirely.)
- **Staged writes are real.** `record_claim` writes to `crucible.claim_staging`,
  never to `crucible.claims`; promotion to durable truth is the approval path
  (Sprint 7). This makes the "gated write" safety property concrete and testable.
- **Search is honest about its mode.** Until Sprint 6 embeddings exist,
  `search_claims` runs a **lexical** match and labels itself `mode: "lexical"`;
  `query_domain_graph`/`get_context_pack` return `degraded: true` when Neo4j is
  empty or down.

## Feature scope

- MCP server process (stdio) via the Python MCP SDK (FastMCP), discoverable by
  `langchain-mcp-adapters` later.
- `ToolService`: `get_dag_node`, `get_run_summary`, `search_claims`,
  `query_domain_graph`, `get_context_pack`, `record_claim` (staged).
- Structured, **bounded-depth** graph query templates (no raw Cypher from input).
- REST `/tools/*` mirror for the UI.
- Docker Postgres + roles + schema init; `pnpm db:up`.
- `crucible.claim_staging` table (declarative + migration).
- shadcn test UI in `apps/web`: Programs (create/list), DAG view, Tools playground.

## Deliverables

- `apps/api/src/autoresearch_api/tools/{service,router,queries}.py`
- `apps/api/src/autoresearch_api/mcp/server.py` (+ `crucible-mcp` script)
- repo methods: lexical claim search + claim-staging insert
- `supabase/migrations/2026..._sprint3_claim_staging.sql` + `01_crucible.sql` update
- `docker-compose.yml` postgres service + `docker/postgres-init/00_roles.sql`
- `apps/web`: Tailwind v4 + shadcn setup, typed API client, three pages
- offline tool tests + safety tests

## Checklist

- [x] MCP server boots and registers all six tools (stdio) — `mcp/server.py`, `crucible-mcp`.
- [x] Every tool goes through repositories / the Neo4j client — no inline SQL/Cypher.
- [x] `query_domain_graph` accepts only `{kind, params}`; templates are fixed and bounded-depth.
- [x] No tool accepts raw SQL/Cypher from input (enforced + tested — `test_tools_queries`).
- [x] Server/REST hold creds; tool results never include connection strings/secrets.
- [x] `get_context_pack` returns `degraded=true` when Neo4j is unavailable (tested).
- [x] `search_claims` returns parameterized lexical results labeled `mode="lexical"` (tested).
- [x] `record_claim` writes to `crucible.claim_staging` only — never `crucible.claims` (tested).
- [x] REST `/tools/*` mirror exposes the read tools + staged `record_claim`.
- [x] Docker Postgres on `:54322` initializes the full schema; `pnpm db:up` brings up the stack.
- [x] shadcn UI: create/list programs, render a DAG, invoke each tool with results + degraded badges.
- [x] Negative tests: invalid ids, unsafe payloads, unavailable Neo4j.

Verified in-sandbox: ruff check + format clean on new backend modules; structured-query
safety + service degraded/staging/lexical/not-found unit tests authored; docker-compose
validates (5 services, Postgres on 54322). **Pending the user's local run**: `uv sync`
(adds `mcp`), `pnpm install` (web deps), `pnpm db:up`, apply migrations, then `api:test`,
`api:dev` + `crucible-mcp`, and `pnpm --filter web dev`.

## Acceptance criteria

- [ ] No tool accepts raw SQL or raw Cypher from model input.
- [ ] MCP server holds credentials; agents receive no connection strings.
- [ ] `get_context_pack` returns `degraded=true` if the graph store is unavailable.
- [ ] Claim search returns ranked results (lexical now; semantic in S6).
- [ ] Tool tests include invalid ids, unsafe query payloads, and unavailable graph store.
- [ ] `pnpm db:up` starts Postgres+Neo4j+Redis+MinIO with no Supabase CLI; live tests pass against it.
- [ ] The web UI can exercise programs, DAG, and every tool end-to-end.

## Definition of Done

Six tools delivered via MCP + REST; zero raw-query paths; degradation cases covered;
Docker-only local stack; the UI demonstrates programs → DAG → tools end-to-end.

## Notes / boundaries

- `get_context_pack` returns a minimal pack now; Sprint 6 enriches it (hybrid
  retrieval) without reshaping the response.
- The MCP server is the agent surface; the REST mirror is for humans/UI. They share
  `ToolService`, so safety is proven once.
