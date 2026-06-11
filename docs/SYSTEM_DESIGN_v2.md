# Crucible v2 — System Design

> **Version:** 2.1 (refined) · **Date:** June 2026
> Companion to [`SRS.md`](./SRS.md). Incorporates [`REFINEMENT.md`](./REFINEMENT.md)
> and consolidates the earlier `DESIGN.md`, `system_design.md`, and
> `ADR-0001-database-architecture.md` (which remain as historical records).
> Build standards: [`CODE_GUIDELINES.md`](./CODE_GUIDELINES.md). Delivery:
> [`sprints/OVERVIEW.md`](./sprints/OVERVIEW.md).

This document specifies **how** the system is built: the runtime substrate, the
state architecture, the orchestration graph, the tool boundary, the context
engine, the execution backends, observability, deployment, and the non-functional
realizations.

---

## 1. Stack decisions

| Concern | Choice | Rationale |
| --- | --- | --- |
| Reasoning runtime | **Raw LangGraph 1.x** (`StateGraph` + LangGraph Server) | Full control of the loop/state/interrupts; removes the Deep Agents beta dependency. The "Deep Agents runtime" role from the SRS is realized directly on LangGraph. |
| Model routing | **`init_chat_model("provider:model")`** | Provider-agnostic; swapping OpenAI/Anthropic/Google/Ollama is a config change, not code. This *is* the reasoning-adapter boundary, so no separate fallback runtime is needed. |
| Tools / data boundary | **MCP server** via `langchain-mcp-adapters` | Parameterized, read-mostly tools; holds DB creds so agents never do. |
| Control plane | **FastAPI** (`apps/api`, uv-managed) | Product API, auth boundary, budgets, approvals, DAG queries, SSE fan-out, replay. The only thing that talks to the runtime. |
| Product plane | **Next.js + Tailwind + shadcn/ui** (`apps/web`) | Shared component lib in `packages/ui`; calls FastAPI only. |
| System of record | **Postgres 16 + pgvector** (schema `crucible`) | Transactional, append-only DAG truth + semantic recall in one engine. |
| Checkpoints | **Postgres** (schema `lg_checkpoints`, `langgraph-checkpoint-postgres`) | Crash recovery / resume; isolated schema so a runtime upgrade can never touch research truth. |
| Domain graph | **Neo4j 5 CE** *(full)* / **Apache AGE** *(lite)* | Native traversal for the 1M-node target; AGE folds the graph into Postgres for one-service self-host. |
| Live streams | **Redis Streams** *(full)* / **Postgres `LISTEN/NOTIFY`** *(lite)* | Real-time trace fan-out, then persisted to `events`. |
| Artifacts | **MinIO/S3** *(full)* / **local FS** *(lite)* | Immutable blobs out of the DB; rows hold refs. |
| Observability | **Pluggable `Tracer`**: Langfuse / OTel (OSS default), LangSmith optional | Self-hostable tracing/cost/evals with no proprietary hard dependency. |
| Embeddings | **Local (`bge-small`/Ollama) default**, API opt-in | Cost + self-host speed; 1536-dim column accommodates either. |
| Execution | **Local / Container** built-in; **Modal / Colab** optional plugins | Default path needs no third-party account; GPU stays pluggable. |
| Monorepo | **Turborepo + pnpm** (TS) and **uv** (Python) | One root workflow; Python services expose `package.json` shims for Turbo. |

---

## 2. Architecture: durable planes

```
                         ┌───────────────────────────────────────┐
                         │            PRODUCT PLANE                │
                         │  Web UI / CLI: DAG · evidence graph ·   │
                         │  traces · cost · approvals · replay     │
                         └───────────────┬───────────────────────┘
                                         │ REST + SSE  (FastAPI only)
                         ┌───────────────▼───────────────────────┐
                         │         CONTROL PLANE (FastAPI)         │
                         │  product API, auth, approvals, budgets, │
                         │  DAG queries, trace/cost fan-out, replay│
                         └───┬───────────────────────────┬─────────┘
              Agent Protocol │ invoke / stream / resume   │ read/write system of record
                         ┌───▼───────────────────────┐    │
                         │   REASONING PLANE          │    │
                         │   LangGraph Server         │    │
                         │   • research-loop graph    │    │
                         │   • proposer subgraph      │    │
                         │   • critic subgraph        │    │
                         │   checkpointer = Postgres  │    │
                         └───┬───────────────┬────────┘    │
            MCP (tools)      │               │ dispatch     │
                         ┌───▼─────────┐ ┌───▼──────────┐   │
                         │  MCP TOOL   │ │  EXECUTION    │   │
                         │  SERVER     │ │  PLANE        │   │
                         │ context+DAG │ │ Local/Container│  │
                         │ read API    │ │ (Modal/Colab) │   │
                         └───┬─────────┘ └───┬──────────┘   │
                             │               │ artifacts/events
        ┌────────────────────▼───────────────▼──────────────▼───────────────┐
        │   STATE LAYER                                                       │
        │   Postgres (crucible truth + lg_checkpoints, separate schemas)      │
        │   Neo4j / AGE (domain graph) · pgvector (recall)                    │
        │   MinIO/S3 / FS (artifacts) · Redis / LISTEN-NOTIFY (live traces)   │
        └─────────────────────────────────────────────────────────────────────┘
```

**Component ownership.**

| Plane | Implemented as | Owns |
| --- | --- | --- |
| Product | Next.js web app + CLI | DAG/evidence/trace/cost/approval/replay views; calls FastAPI only. |
| Control | FastAPI service | Product API, auth boundary, budget enforcement, approval records, DAG/evidence queries, replay orchestration, SSE fan-out. |
| Reasoning | LangGraph Server (self-hosted) | Research-loop graph + proposer/critic subgraphs; resumable execution; HITL interrupts. |
| MCP tool | LangChain-tooled MCP server | Safe, parameterized, read-mostly boundary to context + DAG. Holds DB creds. |
| Execution | `Backend` adapters | Long-running synthesis/GPU jobs. |
| Context | Context Broker worker | Ingestion, extraction, entity resolution, embeddings, graph writes, context-pack generation. |
| State | Postgres / Neo4j(AGE) / pgvector / object store / streams | All durable truth. |

---

## 3. The spine: agent session ≠ research state

The most important invariant. LangGraph gives two kinds of state; they must never
be conflated.

| | LangGraph checkpointer state | Crucible system of record |
| --- | --- | --- |
| What | Per-thread execution snapshot (node state, pending interrupts) | Programs, hypotheses, runs, claims, approvals, budgets, events |
| Purpose | Crash recovery, resume-after-interrupt, time-travel debug | The research result the UI/replay/provenance read |
| Lifetime | Disposable; prunable | Permanent; nodes never deleted |
| Owner | LangGraph (format may change) | Crucible (stable, versioned) |
| Store | Postgres `lg_checkpoints` | Postgres `crucible` + Neo4j/AGE |

**Rule of construction:** a graph node produces a result, then **writes the durable
record to `crucible` / the domain graph before signalling completion**. Drop every
checkpoint and you lose in-flight resumability but **zero research truth**.

**Idempotency:** every durable write is keyed by a deterministic id derived from
`(program_id, parent_id, proposal_hash)`, so a replayed/resumed node is a safe
upsert. Enforced in schema by `UNIQUE NULLS NOT DISTINCT`.

---

## 4. Orchestration: the research-loop graph

One durable LangGraph graph. Nodes are short; long jobs are dispatched out-of-band
and the graph parks on an interrupt until completion.

### 4.1 State (ids and counters only)

```python
class ProgramState(TypedDict):
    program_id: str
    program_type: Literal["literature_synthesis", "ml_experiment"]
    frontier: list[str]            # hypothesis ids eligible to expand (the beam)
    beam_width: int                # adaptive within [min, max]
    budget_remaining_usd: float
    decisions: Annotated[list[Decision], operator.add]   # reducer-merged fan-in
    halt_reason: str | None
```

Content lives in the system of record; nodes fetch by id. Keeps checkpoints tiny.

### 4.2 Topology

```
 START → select_frontier ──(budget ok & frontier≠∅)──┐
            │ Send(expand, h) × beam_width            │
            ▼   (parallel fan-out, map)               │
        expand[h] → proposer subgraph                 │
            ▼                                          │
        novelty_gate  (skip/merge near-duplicates)    │
            ▼                                          │
        run_experiment → dispatch + interrupt() ───────┤ (resume on completion)
            ▼                                          │
        critic → critic subgraph (independent model)  │
            ▼                                          │
        evaluate → keep/reject/quarantine/escalate    │
            ▼                                          │
        approval_gate → interrupt() on escalate/over-budget
            ▼                                          │
        persist → write hypothesis/run/claims to       │
                  crucible + domain graph (fan-in) ────┘ loop
            ▼  (budget exhausted or goal met)
          END
```

### 4.3 Beam-bounded search via `Send`

`select_frontier` picks up to `beam_width` hypotheses and emits one `Send("expand",
{...})` each. LangGraph runs `expand → novelty_gate → run_experiment → critic →
evaluate` in parallel per node and fans results back into `decisions` via
`operator.add`. Beam width is the cost lever and is **adaptive** to budget headroom
and recent kept-rate (REFINEMENT R3.4).

### 4.4 Long jobs without blocking

1. `run_experiment` calls `Backend.submit(job_spec)` → returns `run_id`, writes a
   `runs` row (`status=running`).
2. Node calls `interrupt({"awaiting": run_id})` — LangGraph durably parks the
   thread (checkpoint persisted).
3. Backend/poller posts completion to the control plane; FastAPI resumes with
   `Command(resume=run_result)`.
4. The graph continues at `critic`.

This is LangGraph 1.x durable execution: the thread survives an orchestrator
restart and resumes exactly where it parked. Combined with idempotent writes, this
is the crash-recovery story (NFR-4).

### 4.5 Human-in-the-loop approvals

`escalate` decisions and over-budget runs hit `approval_gate`:
1. Insert an `approvals` row (`pending`, `ttl`, `audit`).
2. `interrupt()` to park the thread.
3. UI/CLI lists pending approvals; approve/deny posts to FastAPI → resumes via
   `Command(resume=...)` and stamps the audit trail.
4. A sweeper resumes with auto-deny on TTL expiry (recorded, never silent).

Approvals are an authorize action — never auto-granted from agent/document text.

---

## 5. Proposer & Critic subgraphs

Each is a separately compiled bounded ReAct-style graph invoked as a node, and is
**stateless w.r.t. research truth**: context pack in → structured object out.

```python
class PatchProposal(BaseModel):
    hypothesis_statement: str
    rationale: str
    artifact_ref: str          # patch diff (ml) or draft answer (lit) → object store
    expected_effect: str
    domain_refs: list[str]     # Neo4j claim/method ids it builds on

class CriticVerdict(BaseModel):
    verdict: Literal["pass", "fail", "revise"]
    gaming_risk: float
    leakage_risk: float
    regression_risk: float
    contradictions: list[str]  # Neo4j claim ids it contradicts
    notes: str
```

- **Structured output** via `with_structured_output` (Pydantic), validated at the
  boundary; a validation failure routes to `revise`, never a loop crash.
- **Model independence:** Critic defaults to a different model family from the
  Proposer; both are configured as two model strings.
- **Disposable:** no conversational memory persists; the only memory is the durable
  context pack + DAG, fetched fresh, plus **success memory** (kept-hypothesis
  few-shot, REFINEMENT R3.2).

---

## 6. Tools, MCP, and the context engine

### 6.1 MCP tool server (the safe boundary)

A standalone MCP server exposes a read-mostly surface; agents reach it through
`MultiServerMCPClient`, which converts MCP tools into LangChain `BaseTool`s.

| Tool | R/W | Purpose |
| --- | --- | --- |
| `get_context_pack(hypothesis_id)` | R | Compact, hybrid-retrieved domain pack (+ `degraded` flag, cached). |
| `query_domain_graph(structured_query)` | R | Parameterized, bounded-depth traversal (no raw Cypher). |
| `search_claims(text, k)` | R | pgvector HNSW semantic recall. |
| `get_dag_node(id)` / `get_run_summary(id)` | R | DAG/run lookups. |
| `record_claim(...)` | W (staged) | Writes to a staging area; durable only via the approval path. |

Safety properties (NFR-6/9): MCP holds DB creds; agents get no secrets or
connection strings; only parameterized queries; writes are staged + gated.

### 6.2 Context engine

```
Context Broker (worker):
  ingest → extract (spaCy spans + LLM claims/relations) → entity-resolve →
  provenance-link → embed → write
        │                  │              │
        ▼                  ▼              ▼
   Neo4j/AGE graph    pgvector recall   object store (sources)
```

- **Domain graph** = relationship-native memory (Paper/Method/Entity/Claim/
  HypothesisSeed with USES/EVALUATES_ON/SUPPORTS/CONTRADICTS/DERIVES_FROM).
- **pgvector** = semantic recall over claims/notes/run summaries (HNSW,
  `vector_cosine_ops`).
- **Hybrid retrieval** (REFINEMENT R3.1): structural (graph) + lexical (full-text)
  + semantic (vector), reranked into the final pack.
- **Broker** runs on program import and after each kept run, feeding new empirical
  claims back so later proposals are conditioned on accumulated evidence.
- **Graceful degradation** (NFR-5): if the graph store is down, `get_context_pack`
  falls back to lexical+semantic from Postgres, flags `degraded=true`, and the loop
  continues.
- **Extraction**: spaCy entity spans + an LLM extraction pass for claims/relations,
  behind the Broker boundary so a dedicated model can replace the LLM pass later.

---

## 7. Execution backends

Pluggable behind one protocol; agent sandbox and experiment backend stay distinct
(NFR-7).

```python
class Backend(Protocol):
    def submit(self, job: JobSpec) -> str: ...        # returns run_id
    def status(self, run_id: str) -> JobStatus: ...
    def fetch_artifacts(self, run_id: str) -> ArtifactRef: ...
    def stream_events(self, run_id: str) -> Iterator[Event]: ...
```

| Layer | Tooling | Use |
| --- | --- | --- |
| Agent sandbox | LangGraph sandbox tools | Git, file I/O, tiny scripts used *during reasoning*. |
| Execution backend | **Local / Container** (built-in); **Modal / Colab** (optional plugins) | Synthesis jobs (lit) and training/eval (ml). |

- For `literature_synthesis`, the "experiment" is a **retrieve+read+synthesize**
  job with no GPU — runs on `LocalBackend`/`ContainerBackend`.
- Artifacts → object store; rows store refs. Live events → streams → `events`.
- Backend selection is per-program config (`research.yaml`). Optional backends are
  discovered via entry points and are not core dependencies.

---

## 8. Data model and indexing

Postgres is the source of truth; the domain graph augments it. See
[`SRS.md` §4](./SRS.md) for the authoritative column list and `supabase/schemas/`
for DDL.

**Hitting the NFR targets:**

- **DAG < 100 ms @ 10k nodes:** adjacency list (`parent_id`) + `hypothesis_closure`
  (AFTER-INSERT trigger) for O(depth) subtree/ancestor reads; covering index
  `(program_id, parent_id, status, depth)`. No recursive CTE on the hot path.
- **Domain graph < 200 ms @ 1M nodes:** composite + full-text indexes on natural
  keys; **bounded-depth** traversals in MCP templates.
- **pgvector:** HNSW index on `claims.embedding`; per-query `ef_search` for the
  recall/latency trade.
- **Context-pack cache:** keyed `(hypothesis_id, domain_graph_version)`, short TTL,
  invalidated on new program claims.

**Cross-store consistency** is application logic: write-truth-before-complete,
idempotent upserts, and a `degraded` flag when the graph store is unavailable.

---

## 9. Observability & evaluation

Tracing is automatic for every graph/subgraph run via the pluggable `Tracer`
boundary (Langfuse/OTel default; LangSmith optional). Each proposer/critic/
evaluator invocation is a trace; `runs.trace_id` links it to the DAG node so the UI
can round-trip node↔trace.

**Three evaluation jobs** (datasets + evaluators):

1. **Critic reliability** — curated gamed/leaky/regressed proposals with known-bad
   labels; metric = catch rate. **Gates** any expansion of the agent count past
   two.
2. **Proposer quality** — held-out hypotheses scored on whether proposals improve
   the primary metric.
3. **Regression + cost CI** — the demo program runs in CI; per-run token/$ feeds
   (a) runtime budget enforcement (`budgets.spent_usd`) and (b) a **CI gate** that
   fails the build if demo cost drifts above the < $20 target.

The whole observability stack runs inside the deployment (OSS/single-tenant).

---

## 10. API surface

**Control plane (FastAPI):**

```
GET  /health                   # {"status":"ok"}
GET  /health/dependencies      # per-store probe (Postgres, graph, streams, object store)
POST /programs                 # import research.yaml, kick off the loop
GET  /programs/{id}            # program detail + budget
GET  /programs/{id}/dag        # DAG (server-aggregated, cursor-paged, virtualized)
GET  /hypotheses/{id}          # node detail (+ trace link)
GET  /runs/{id}                # run detail, score vector, artifacts
POST /runs                     # dispatch a run (backend)
GET  /approvals?status=pending
POST /approvals/{id}/decide    # approve/deny → resumes the parked thread
GET  /programs/{id}/stream     # SSE: live traces/events/cost
POST /runs/{id}/replay         # re-execute a kept run deterministically
```

The **reasoning plane** is reached only through LangGraph Server's REST + SSE /
Agent Protocol; FastAPI is the sole caller. The UI/CLI never call the runtime,
Neo4j, Redis, or Postgres directly.

---

## 11. Deployment

### 11.1 Profiles

| | `lite` (laptop / first run) | `full` (production-grade) |
| --- | --- | --- |
| Services | **1** (Postgres+pgvector+AGE) | **4** (Postgres, Neo4j, Redis, MinIO) |
| Graph | Apache AGE in Postgres | Neo4j 5 CE |
| Streams | `LISTEN/NOTIFY` | Redis Streams |
| Artifacts | Local FS volume | MinIO/S3 |
| Same MCP API & repos | yes | yes |

Both come up with `docker compose --profile <lite|full> up`. Application code does
not branch on profile; only wiring/config does.

### 11.2 Local vs hosted

- **Local:** Supabase CLI (Postgres 15 locally) + `infra:up` for the `full` extra
  services. `cp .env.example .env`.
- **Hosted:** `.env.hosting.example` template; the app server needs a direct
  Supabase Postgres `DATABASE_URL` that is **never** exposed via `NEXT_PUBLIC_*` or
  shipped to the browser. Managed Neo4j/Redis/S3 recommended; deploy DB changes via
  `supabase db push`.

### 11.3 Monorepo layout

```
apps/
  api/     FastAPI control plane (uv)            ← + agent/ graph package, mcp/ server
  web/     Next.js product UI (Tailwind+shadcn)
  docs/    Next.js docs app
packages/
  ui/                shared shadcn/ui components + tokens
  eslint-config/     shared lint
  typescript-config/ shared tsconfig
schema/neo4j/        CE-compatible constraints + indexes
supabase/            config, declarative schemas, migrations
tools/               offline validators
examples/            nanochat (ml) + lit-synthesis (deep research) programs
```

Python services expose `package.json` shims so Turbo runs one root workflow while
uv manages Python deps.

---

## 12. Non-functional realization (summary)

| Requirement | How |
| --- | --- |
| Crash recovery (NFR-4) | LangGraph durable execution + Postgres checkpointer; idempotent durable writes keyed on proposal hash. |
| Graph degradation (NFR-5) | Lexical+semantic Postgres fallback with `degraded=true`. |
| Secret isolation (NFR-6) | Creds in MCP/backends/API; agents get tools, never secrets/connection strings/raw queries. |
| Sandbox isolation (NFR-7) | Agent sandbox separate from exec backends; no shared creds. |
| Portability (NFR-8) | `lite`/`full` compose profiles; runtime/backend/tracer/embeddings swappable behind interfaces. |
| Replay (NFR-9) | Immutable artifact/event/context-snapshot refs; opt-in determinism. |
| Large DAG (NFR-10) | Server aggregation + cursor paging + virtualization; WCAG 2.1 AA. |
| Traceability (NFR-11) | Pluggable tracer; `runs.trace_id` links DAG↔trace. |

---

## 13. Trade-offs & what to revisit

- **Loop-as-graph vs. FastAPI-owns-the-loop.** Chose loop-as-graph (matches
  "LangGraph for orchestration"; free durability/HITL). *Revisit* for many
  concurrent programs with heavy cross-program scheduling → thin external scheduler
  calling per-expansion graphs.
- **Checkpointer = Postgres.** One fewer service. *Revisit* (Redis/Mongo) only if
  checkpoint write volume becomes a hotspot.
- **Neo4j CE / AGE.** No HA. Degradation is mandatory. *Revisit* (Enterprise or
  other graph store) only if HA becomes a real requirement (out of scope for v2).
- **State holds ids, not content.** Tiny checkpoints, truth in the DB, at the cost
  of extra fetches per node — the right trade given the spine rule.
- **Structured output everywhere.** Slightly more brittle to model quirks; the
  price of a stable, auditable boundary. Validation failures route to `revise`.

---

## 14. Implementation status (as of this revision)

**Built (Sprints 0–1, `Done`):** Postgres `crucible` schema (8 tables, closure
trigger, idempotency key, pgvector column, RLS, private grants); `lg_checkpoints`
boundary; Neo4j CE constraints/indexes; Docker Compose for Neo4j/Redis/MinIO +
bucket init; FastAPI health + dependency probes; typed repositories for the core
tables + Neo4j/Redis/S3 wrappers; local + hosting env templates; offline DB
validator.

**Not built yet:** product API beyond health; MCP server; LangGraph research-loop;
Context Broker + embeddings; backends; approval/resume; replay; web UI; CI + live
integration; the `lite` profile (AGE/LISTEN-NOTIFY/FS) and pluggable tracer/
embeddings adapters introduced by this refinement.

See [`sprints/OVERVIEW.md`](./sprints/OVERVIEW.md) for the sequenced plan.

---

*End of Crucible v2 system design (refined v2.1).*
