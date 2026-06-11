# Crucible v2 — Code Guidelines

> The standard every contributor (human or agent) follows when writing code in
> this repo. These rules are derived from the existing codebase, the
> [`SYSTEM_DESIGN_v2.md`](./SYSTEM_DESIGN_v2.md) boundaries, and the
> [`SRS.md`](./SRS.md) non-functional requirements. When a rule here conflicts
> with convenience, the rule wins — clean, auditable boundaries are the product.

---

## 0. Prime directives (read these first)

1. **The agent session is not the research state.** Never write durable research
   truth into LangGraph state/checkpoints. Truth goes to the `crucible` schema /
   domain graph / object store. Checkpoints are disposable.
2. **Write durable truth *before* a graph node signals completion**, and make
   every durable write idempotent on `(program_id, parent_id, proposal_hash)`.
3. **Secrets never reach an agent.** Credentials, connection strings, and raw
   SQL/Cypher live in FastAPI, the MCP server, and backends — never in prompts,
   tool results, or `NEXT_PUBLIC_*`.
4. **The UI/CLI talk to FastAPI only.** They never touch LangGraph Server, Neo4j,
   Redis, or Postgres directly.
5. **No raw query strings from models or untrusted input.** Only parameterized
   queries and bounded-depth graph templates.
6. **Respect the layer boundaries.** Behind every external dependency
   (model, tracer, embeddings, backend, graph store, streams, object store) sits an
   interface. Depend on the interface, not the implementation.

---

## 1. Repository structure & tooling

- **Monorepo:** Turborepo + pnpm for TS; **uv** for Python. One root workflow.
- **Python services** expose a `package.json` shim so Turbo can run them; uv owns
  Python deps. Do not add a second Python dependency manager.
- **Root scripts** are the canonical entry points — use them, don't reinvent:
  `pnpm api:dev`, `pnpm api:check`, `pnpm api:test`, `pnpm api:test:live`,
  `pnpm db:validate`, `pnpm db:supabase:start`, `pnpm infra:up`,
  `pnpm check-types`, `pnpm lint`, `pnpm format`.
- **Never commit** `.venv/`, `.turbo/`, `.ruff_cache/`, `node_modules/`,
  `__pycache__/`, build output, `bash.exe.stackdump`, or local Sprint execution
  reports (`docs/Sprint_*.md` are gitignored on purpose).

---

## 2. Python (the backend, agents, MCP, backends, broker)

### 2.1 Language level & style

- **Python 3.12+.** `requires-python = ">=3.12"`.
- **Ruff is the linter & formatter.** Config (already set): `line-length = 100`,
  `target-version = "py312"`, lint rules `E, F, I, UP, B, SIM`. Run
  `uv run --project apps/api ruff check apps/api/src` before every commit; it must
  pass clean (no `# noqa` without a reason comment).
- **`from __future__ import annotations`** at the top of every module.
- **Type hints everywhere.** Public functions are fully annotated. Prefer modern
  syntax (`str | None`, `list[str]`, `dict[str, Any]`) — that's why `UP` is on.
- **No bare `except`.** Catch specific exceptions; map DB errors to the project's
  typed errors (`DataNotFoundError`, `DataConflictError`) — see `db/errors.py`.

### 2.2 Data shapes

- **Immutable records:** read models are `@dataclass(frozen=True)` (see
  `db/repositories.py`). Don't mutate records; build new ones.
- **Validated boundaries:** anything crossing an API or agent boundary is a
  **Pydantic** model (`PatchProposal`, `CriticVerdict`, request/response models).
  Agent outputs use `with_structured_output` — never parse free text.
- **Settings:** all config via `pydantic-settings` `Settings` (see `settings.py`),
  loaded once through the `@lru_cache get_settings()` accessor. No `os.environ`
  reads scattered through the code, and no hardcoded hosts/ports/creds.

### 2.3 Database access

- **All SQL is parameterized** through `asyncpg` (`$1, $2, …`). Never f-string or
  `.format()` a value into SQL/Cypher. This is a security requirement, not a style
  preference.
- **Repositories own SQL.** Routes/graph nodes call repository methods; they do not
  embed SQL. One repository concern per table family (programs, hypotheses, runs,
  claims, budgets, approvals, events).
- **Connection lifecycle:** pools are created/closed in the app lifespan
  (`postgres.py`); never open ad-hoc connections in a request/node.
- **Schema discipline:** product truth in schema `crucible`; LangGraph checkpoints
  in `lg_checkpoints`. Never read `lg_checkpoints` as product data. Every
  product table keeps RLS enabled and is reached through server-side creds only.
- **Migrations:** declarative SQL in `supabase/schemas/`, versioned migration in
  `supabase/migrations/`. Past the v0 baseline, schema changes ship as a new
  migration — never edit an applied migration. Run `pnpm db:validate` after any
  schema change.
- **Graph store:** Neo4j/AGE access goes through the graph repository with
  **bounded-depth** parameterized templates. Community Edition can't enforce
  property existence — the app enforces required properties on write.

### 2.4 FastAPI

- **Thin routes.** A route validates input (Pydantic), calls a service/repository,
  maps domain errors to HTTP, and returns a response model. No business logic in
  routes.
- **Dependency injection** via `dependencies.py`; resources come from the shared
  providers, not module globals.
- **Errors** map through `db/errors.py` to explicit HTTP responses with stable
  shapes. Don't leak driver exceptions or stack traces to clients.
- **Health:** keep `GET /health` and `GET /health/dependencies` honest — each
  configured store probed explicitly.

### 2.5 Async

- **Async-first.** I/O (DB, HTTP, streams, object store) is `async`. Don't block
  the event loop with sync I/O or CPU-heavy work — offload CPU work (embeddings,
  extraction) to the Broker/worker, not a request handler or graph node.
- **`asyncio_mode = "auto"`** for tests; mark live-DB tests behind
  `AUTORESEARCH_RUN_LIVE_DB_TESTS=1` so the default suite needs no Docker.

### 2.6 LangGraph nodes

- **Nodes are short.** Long jobs dispatch to a `Backend` and `interrupt()`; never
  block a node for minutes.
- **State holds ids and counters, not content.** Fetch content by id from the
  system of record inside the node.
- **Persist-before-complete + idempotent upsert** in every node that produces
  durable truth.
- **Subgraphs are stateless w.r.t. research truth:** context pack in → structured
  object out. No hidden conversational memory.

---

## 3. TypeScript / Next.js (web, docs, packages)

### 3.1 Language & lint

- **TypeScript strict.** Use the shared `packages/typescript-config`. No `any`
  except at the very edge with a justification comment; prefer `unknown` + narrow.
- **ESLint** via `packages/eslint-config`; **Prettier** for formatting
  (`pnpm format`). `pnpm check-types` must pass.
- **No default-exporting** shared utilities; named exports for tree-shaking.
  (Exception: React route/page components per Next.js conventions.)

### 3.2 Frontend architecture

- **Server boundary:** the web app calls **FastAPI** through a single typed client
  module. No direct DB/runtime calls. Server-only secrets stay server-side; only
  `NEXT_PUBLIC_*` reaches the browser, and those never contain credentials.
- **Design system:** Tailwind + **shadcn/ui** components live in `packages/ui` and
  are shared by `web` and `docs`. Define design tokens once (teal `--primary:
  #0d5c63`, IBM Plex type, light/dark) and consume them — no ad-hoc hex values in
  components.
- **DAG rendering:** always server-aggregated + paged + virtualized. Never render a
  raw 5k+ node tree client-side (NFR-10). Use React Flow for moderate trees, a WebGL
  renderer past the node threshold.
- **Data fetching:** prefer Server Components / server actions for reads; stream
  live updates over SSE with reconnect+backoff. Keep client state minimal.
- **Accessibility:** WCAG 2.1 AA — semantic HTML, keyboard nav, focus order, visible
  focus, `prefers-reduced-motion` for the graph canvas.

---

## 4. Security & secrets (non-negotiable)

- Secrets only in server-side env (`.env`, deployment secrets). Never in client
  bundles, prompts, tool results, logs, or the repo.
- The MCP server holds DB creds; agents receive tools, never connection strings or
  raw query languages.
- Staged writes (`record_claim`) become durable **only** through the approval path.
- Dangerous/expensive actions require an `approvals` record — never auto-granted
  from anything an agent or document says.
- Validate and bound every external input (program specs, URLs to ingest, tool
  args). Treat ingested documents and model output as untrusted.

---

## 5. Testing

- **Pytest** (`asyncio_mode=auto`), tests in `apps/api/tests`. Offline unit tests
  must run with **no live services**; live-DB tests are gated by
  `AUTORESEARCH_RUN_LIVE_DB_TESTS=1`.
- **Test the boundary, not the framework.** Cover: idempotent upserts, closure-row
  population, error mapping, structured-output validation + `revise` fallback,
  degradation paths (graph store down), and approval resume/expiry.
- **Negative tests are required** for the MCP tools: reject raw SQL/Cypher, invalid
  ids, unavailable graph store.
- Every new feature ships with tests that assert its acceptance criteria from the
  relevant sprint doc. A sprint is not `Done` until its acceptance tests pass.
- Frontend: type-check is the floor; add component/interaction tests for the DAG,
  approvals, and trace panel.

---

## 6. Errors, logging, observability

- **Typed domain errors** (`db/errors.py`) at boundaries; map to HTTP/CLI messages.
- **Structured logging** (no secrets, no full prompts). Log ids, statuses,
  durations, costs — not payloads.
- **Tracing** goes through the pluggable `Tracer`; every proposer/critic/evaluator
  invocation is traced and linked via `runs.trace_id`. Don't hardcode a tracer
  vendor.

---

## 7. Git & reviews

- **Conventional Commits:** `feat:`, `fix:`, `docs:`, `refactor:`, `test:`,
  `chore:`, `perf:`, `ci:`. Scope where useful (`feat(api): …`, `feat(agent): …`).
- **Small, reviewable PRs** tied to a sprint checklist item; the PR description
  links the acceptance criteria it satisfies.
- **Green before merge:** `pnpm check-types`, `pnpm lint`, `pnpm api:check`, ruff,
  and `pnpm db:validate` (when schema touched) must pass. CI (Sprint 9) enforces
  this.
- **No commented-out code, no dead code, no TODOs without an issue link.**
- Update the relevant doc (`SRS`, `SYSTEM_DESIGN_v2`, sprint doc) in the same PR
  when behavior or contracts change.

---

## 8. Performance budgets (enforce, don't hope)

- DAG ancestor/subtree reads from the closure table only (< 100 ms @ 10k nodes).
- Domain-graph traversals bounded-depth + indexed (< 200 ms @ 1M nodes).
- pgvector HNSW for recall; tune `ef_search` per query.
- Cache context packs; batch embeddings; never embed inline in a graph node.
- Keep the overnight demo under the < $20 cost guard; the CI cost gate fails on
  drift.

---

## 9. Definition of "clean" for this repo

A change is clean when: it respects the prime directives (§0), passes ruff +
types + tests, adds no secret-exposure surface, keeps truth/checkpoint separation
intact, depends on interfaces not implementations, and updates the doc it changed.
If you can remove code and keep the behavior, remove it.

---

*Keep this file short and enforced. If a guideline isn't being followed, either fix
the code or change the guideline — don't let it rot.*
