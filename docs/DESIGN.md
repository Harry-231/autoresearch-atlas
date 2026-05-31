# Crucible v2 — System Design

> Companion to the Software Requirements Specification (SRS v2.0, May 2026).
> This document specifies *how* the system is built, on a **LangGraph / LangChain / LangSmith** stack, as an open-source project.

---

## 0. Stack decision vs. the SRS

The SRS names **"LangChain Deep Agents Deploy"** as the reasoning runtime. This design realizes that same role on **raw LangGraph 1.x** instead, with LangChain for tools/MCP and LangSmith for tracing/evals.

| SRS term | What we build it on | Why |
| --- | --- | --- |
| Deep Agents runtime | LangGraph `StateGraph` + LangGraph Server | Deep Agents is a LangGraph-based harness; using LangGraph directly removes a beta dependency layer (SRS Risk: *"Deep Agents beta churn"*) and gives full control over the loop, state, and interrupts. |
| `deepagents.toml` / `AGENTS.md` / `subagents/` | `langgraph.json` + compiled subgraphs + per-agent prompt/model config | Same packaging intent, native to the chosen runtime. |
| Native Deep Agents sandbox | LangGraph sandbox tools *for agent-side code only* | Unchanged in spirit — see §8, the agent sandbox is **not** the GPU backend. |
| REST + SSE / MCP / Agent Protocol | LangGraph Server (REST+SSE, Agent Protocol) + `langchain-mcp-adapters` | All first-class in the LangGraph ecosystem as of 2026. |

Everything else in the SRS — Postgres as durable truth, Neo4j domain graph, pluggable GPU backends, beam-bounded proposer/critic search, replay, budgets, approvals — is preserved verbatim in intent.

**Net effect on the SRS open question** *"Should v2 ship a parallel fallback reasoning adapter?"* — choosing raw LangGraph already gives you a thin model/agent boundary (see §6), so a separate fallback runtime is no longer load-bearing.

---

## 1. Requirements recap

**Functional (what it does).** Run autonomous, reproducible research programs: ingest papers + a spec, grow a durable hypothesis DAG via a Proposer/Critic loop under beam-bounded search, score each hypothesis on multiple metrics, gate expensive/risky work behind human approval, and expose DAG / evidence-graph / trace / replay views.

**Non-functional (the hard numbers).**
- DAG queries < 100 ms for 10k-node trees.
- Domain-graph queries < 200 ms for 1M-node graphs.
- Overnight cost target < $20/program (LLM < $10, GPU $5–8).
- Crash-recoverable orchestrator; replayable "kept" runs; graceful degradation if Neo4j is down.
- Secrets never enter agent prompts; dangerous actions require approval.

**Constraints.** OSS, single-tenant, self-hostable with Docker Compose. No multi-tenant SaaS, no domain packs, no >2-agent swarm in v2. Neo4j **Community Edition** (single instance — no clustering/HA, which raises the stakes on graceful degradation).

---

## 2. Architecture overview

Four durable planes, exactly as the SRS, with the runtime substrate made concrete.

```
                         ┌───────────────────────────────────────┐
                         │            PRODUCT PLANE                │
                         │   Web UI: DAG · evidence graph ·        │
                         │   traces · approvals · replay           │
                         └───────────────┬───────────────────────┘
                                         │ REST + SSE
                         ┌───────────────▼───────────────────────┐
                         │         CONTROL PLANE (FastAPI)         │
                         │  product/API, auth, approvals, budgets, │
                         │  DAG queries, trace fan-out, replay      │
                         └───┬───────────────────────────┬─────────┘
                             │ invoke / stream            │ read/write system of record
              Agent Protocol │ (threads, runs, interrupts)│
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
                         │ context+DAG │ │ Local/Modal/  │   │
                         │ read API    │ │ Colab backends│   │
                         └───┬─────────┘ └───┬──────────┘   │
                             │               │ artifacts/events
        ┌────────────────────▼───────────────▼──────────────▼───────────────┐
        │   STATE LAYER                                                       │
        │   Postgres (system of record + LG checkpoints, separate schemas)    │
        │   Neo4j (domain graph) · pgvector (semantic recall)                 │
        │   MinIO/S3 (artifacts) · Redis Streams (live traces → DB)           │
        └─────────────────────────────────────────────────────────────────────┘
```

**Component ownership.**

| Component | Implemented as | Owns |
| --- | --- | --- |
| Control plane | FastAPI service | Product API, auth, budget enforcement, approval records, DAG/evidence queries, replay orchestration, SSE trace fan-out. |
| Reasoning plane | LangGraph Server (self-hosted standalone) | The research-loop graph + proposer/critic subgraphs; resumable execution; HITL interrupts. |
| MCP tool server | LangChain-tooled MCP server (stdio + HTTP) | Safe, read-mostly boundary to context + DAG for agents. Holds DB creds so agents never do. |
| Execution plane | `Backend` adapters (Local/Modal/Colab) | Long-running GPU training/eval/sim jobs. |
| Context Broker | Async worker (optionally its own LangGraph graph) | Paper/claim ingestion, entity resolution, context-pack generation. |
| State layer | Postgres / Neo4j / pgvector / MinIO / Redis | All durable truth. |

---

## 3. The spine: agent session ≠ research state

This is the most important decision in the system, and the one most LangGraph projects get wrong. The SRS rule is:

> *Agent invocations are disposable workers. The durable truth lives in Postgres, Neo4j, object storage, and replayable execution metadata.*

LangGraph gives us **two** kinds of state, and we must never conflate them:

| | LangGraph checkpointer state | Crucible system of record |
| --- | --- | --- |
| What it is | Per-thread execution snapshot (graph node state, pending interrupts) | Programs, hypotheses, runs, claims, approvals, budgets |
| Purpose | Crash recovery, resume-after-interrupt, time-travel debugging | The research result; what the UI, replay, and provenance read from |
| Lifetime | Disposable; can be pruned/expired | Permanent; nodes are never deleted |
| Schema owner | LangGraph (format may change between versions) | Crucible (stable, versioned, ours) |
| Store | Postgres schema `lg_checkpoints` (via `langgraph-checkpoint-postgres`) | Postgres schema `crucible` + Neo4j |

**Rule of construction:** a graph node produces a result, then **writes the durable record to the `crucible` schema / Neo4j before signalling completion**. The checkpoint is only a recovery aid. If you dropped every checkpoint, you would lose in-flight resumability but **zero research truth**.

**Why separate schemas (and ideally separate logical DBs):** it decouples our permanent data model from LangGraph's internal checkpoint format, so a runtime upgrade can never corrupt or migrate the system of record. This is the concrete, code-level version of the SRS's "reasoning adapter boundary."

**Idempotency:** every durable write is keyed by a deterministic id derived from `(program_id, parent_id, proposal_hash)` so that a replayed/resumed node is a safe upsert, not a duplicate.

---

## 4. Orchestration: the research-loop graph

The research program is modelled as **one durable LangGraph graph** (honoring "LangGraph for orchestration") whose nodes are short, with long GPU work dispatched out-of-band and the graph *parked on an interrupt* until the job finishes.

### 4.1 Graph state

```python
class ProgramState(TypedDict):
    program_id: str
    frontier: list[str]          # hypothesis ids eligible to expand (the beam)
    beam_width: int
    budget_remaining_usd: float
    decisions: Annotated[list[Decision], operator.add]  # reducer-merged fan-in
    halt_reason: str | None
```

Note the state holds **ids and counters, not research content**. Content lives in the system of record; nodes fetch what they need by id. This keeps checkpoints tiny and keeps truth in Postgres/Neo4j.

### 4.2 Topology

```
        START
          │
          ▼
   ┌──────────────┐     budget ok & frontier ≠ ∅
   │ select_      │◄──────────────────────────────┐
   │ frontier     │                                │
   └──────┬───────┘                                │
          │ Send(expand, h) × beam_width           │
   ┌──────▼───────┐  (parallel fan-out, map)       │
   │  expand[h]   │  → proposer subgraph            │
   └──────┬───────┘                                │
          │                                         │
   ┌──────▼───────┐                                 │
   │ run_         │  dispatch GPU job, then         │
   │ experiment   │  interrupt() until callback     │
   └──────┬───────┘                                 │
   ┌──────▼───────┐                                 │
   │   critic     │  critic subgraph (other model)  │
   └──────┬───────┘                                 │
   ┌──────▼───────┐                                 │
   │  evaluate    │  multi-metric → keep/reject/    │
   │              │  quarantine/escalate            │
   └──────┬───────┘                                 │
   ┌──────▼───────┐  escalate → interrupt()         │
   │ approval_    │  (human gate, see §4.5)         │
   │ gate         │                                 │
   └──────┬───────┘                                 │
   ┌──────▼───────┐  write DAG node, run, claims    │
   │  persist     │  to crucible schema + Neo4j     │
   └──────┬───────┘  (reduce / fan-in)              │
          │ loop ──────────────────────────────────┘
          ▼  (budget exhausted or goal met)
         END
```

### 4.3 Beam-bounded search via the `Send` API

`select_frontier` picks up to `beam_width` hypotheses and emits one `Send("expand", {"hypothesis_id": h})` per node. LangGraph runs the `expand → run_experiment → critic → evaluate` branch in parallel for each, then fans results back into `decisions` via the `operator.add` reducer. The beam width is the cost lever; combined with context compaction it keeps spend in the SRS's target class while exploring wider than a linear loop.

### 4.4 Long-running GPU work without blocking the graph

A graph node must not block for hours. Pattern:

1. `run_experiment` calls `Backend.submit(job_spec)` → returns a `run_id`, writes a `runs` row (`status=running`).
2. Node calls `interrupt({"awaiting": run_id})` — LangGraph durably parks the thread (checkpoint persisted).
3. The backend (or a poller) posts completion to the control plane; FastAPI resumes the thread with `Command(resume=run_result)`.
4. The graph continues at `critic` with the result in hand.

This uses LangGraph 1.x **durable execution** — the thread survives an orchestrator restart and resumes exactly where it parked. Combined with idempotent writes (§3), this is the crash-recovery story.

### 4.5 Human-in-the-loop approvals

`escalate` decisions and over-budget runs hit `approval_gate`, which:
1. Inserts an `approvals` row (`status=pending`, `ttl`, `audit` jsonb) in the system of record.
2. Calls `interrupt()` to park the thread.
3. The UI lists pending approvals; an approve/deny posts to FastAPI, which resumes via `Command(resume=...)` and stamps the audit trail.
4. TTL expiry → a sweeper resumes with an auto-deny.

The durable approval record is **Crucible's**; the `interrupt` is just the runtime mechanism. (Approvals are an *expand-audience / authorize* action — never auto-granted from anything an agent or document "says.")

---

## 5. Proposer & Critic subgraphs

Each is a separately compiled graph (a bounded ReAct-style agent) invoked as a node. They are **stateless w.r.t. research truth**: context pack in → structured object out.

```
Proposer:  context_pack ──► [model A + MCP read tools] ──► PatchProposal
Critic:    proposal+run  ──► [model B + MCP read tools] ──► CriticVerdict
```

```python
class PatchProposal(BaseModel):
    hypothesis_statement: str
    rationale: str
    patch_diff: str                 # stored to MinIO; row holds the ref
    expected_effect: str
    domain_refs: list[str]          # Neo4j claim/method ids it builds on

class CriticVerdict(BaseModel):
    verdict: Literal["pass", "fail", "revise"]
    gaming_risk: float
    leakage_risk: float
    regression_risk: float
    contradictions: list[str]       # Neo4j claim ids it contradicts
    notes: str
```

- **Structured output** via `with_structured_output` (Pydantic) — no prompt-scraping, validated at the boundary.
- **Model independence:** Critic defaults to a *different model family* (e.g. proposer on OpenAI, critic on Anthropic/Google). Config is just two model strings — LangChain's `init_chat_model("provider:model")` gives provider-agnostic routing, so swapping providers is a config change, not a code change.
- **Disposable:** no conversational memory persists between invocations. The only "memory" is the durable context pack and DAG, fetched fresh.

---

## 6. Tools, MCP, and the context engine

### 6.1 MCP tool server (the safe boundary)

A standalone MCP server exposes a **read-mostly** surface; agents reach it through `langchain-mcp-adapters` `MultiServerMCPClient`, which converts MCP tools into LangChain `BaseTool`s usable inside the subgraphs.

| Tool | R/W | Purpose |
| --- | --- | --- |
| `get_context_pack(hypothesis_id)` | R | Compact domain pack: relevant claims, methods, contradictions, prior run summaries. |
| `query_domain_graph(structured_query)` | R | Parameterized Neo4j traversal (no raw Cypher from the model). |
| `search_claims(text, k)` | R | pgvector semantic recall. |
| `get_dag_node(id)` / `get_run_summary(id)` | R | DAG/run lookups. |
| `record_claim(...)` | W | Gated: writes proposed claims to a staging area, never directly to truth. |

Critical safety properties (SRS §Security):
- The MCP server holds DB credentials; **agents never receive secrets** and never get raw connection strings.
- Only **parameterized** queries are exposed — no arbitrary Cypher/SQL from a model.
- Writes are staged + require the normal approval path before becoming durable truth.

This directly answers the SRS Risk on Neo4j complexity: agents see a stable, narrow tool API, not the graph internals.

### 6.2 Context engine

```
                 ┌──────────────── Context Broker (worker / LangGraph graph) ─────────────┐
   papers, ──►   │ ingest → extract (claims/methods/entities) → entity-resolve →           │
   run outputs   │ provenance-link → embed → write                                         │
                 └──────────┬───────────────────────────────┬───────────────┬─────────────┘
                            ▼                                 ▼               ▼
                     Neo4j domain graph              pgvector (recall)   MinIO (sources)
   Paper ─USES→ Method
   Paper ─EVALUATES_ON→ Entity
   Claim ─SUPPORTS/CONTRADICTS→ Claim
   HypothesisSeed ─DERIVES_FROM→ Claim
```

- **Neo4j** = relationship-native domain memory (papers, methods, entities, claims, contradictions, hypothesis seeds).
- **pgvector** = semantic recall over notes, run summaries, embedded claims.
- **Context Broker** runs on program import and after each kept run, feeding new empirical claims back into the graph — closing the loop so later proposals are conditioned on accumulated evidence.
- **Graceful degradation:** if Neo4j is unavailable, `get_context_pack` falls back to a pgvector-only pack and flags `degraded=true`; the program continues with lower domain confidence rather than halting (SRS reliability requirement).

> SRS open question — *spaCy+LLM vs. dedicated extraction model.* Recommendation: ship **spaCy for entity spans + an LLM extraction pass for claims/relations** in v2; the boundary is internal to the Broker so a dedicated model can replace the LLM pass later without touching the graph schema.

---

## 7. Execution backends

Pluggable behind one interface; agent sandbox and GPU backend stay distinct (SRS callout).

```python
class Backend(Protocol):
    def submit(self, job: JobSpec) -> str: ...        # returns run_id
    def status(self, run_id: str) -> JobStatus: ...
    def fetch_artifacts(self, run_id: str) -> ArtifactRef: ...
    def stream_events(self, run_id: str) -> Iterator[Event]: ...
```

| Layer | Tooling | Use |
| --- | --- | --- |
| Agent sandbox | LangGraph sandbox tools | Git, file I/O, tiny scripts, bounded code tools used *during reasoning*. |
| Execution backend | Local / Modal / Colab | Training, replay, benchmark eval, long GPU jobs. |

- **Artifacts** (diffs, checkpoints, logs) → MinIO/S3; the DB stores only refs.
- **Live events** → Redis Streams, fanned to the UI via SSE, then persisted to `events` for replay.
- **Backend selection** is per-program config (`research.yaml`), matching the SRS phasing (Local → Modal → Colab).

---

## 8. Data model

Postgres remains the source of truth; Neo4j augments it. New vs. the SRS: explicit linkage columns to the LangGraph thread/run and the LangSmith trace, so the UI can jump from a DAG node to its full execution trace and back.

```sql
-- schema: crucible (system of record)
programs(id, name, version, spec_yaml, neo4j_graph_id, created_at, owner)

hypotheses(id, program_id, parent_id, depth, status,
           patch_diff_ref, compact_summary,
           lg_thread_id,            -- LangGraph thread that produced it
           proposer_run_id,         -- LangSmith run id (proposer)
           neo4j_context_ref, created_at)

runs(id, hypothesis_id, backend, status, started_at, ended_at,
     score_vector_json, critic_verdict_json,
     artifacts_ref, event_log_ref,
     langsmith_trace_id,            -- jump-to-trace
     neo4j_context_snapshot_ref)

claims(id, hypothesis_id, run_id, statement, source_artifact_ref,
       confidence, neo4j_claim_id, embedding vector)

approvals(id, run_id, kind, status, ttl, requested_at, decided_at, decided_by, audit jsonb)
budgets(id, program_id, cap_usd, spent_usd, updated_at)
events(id, run_id, ts, kind, payload jsonb)

-- schema: lg_checkpoints  (owned by LangGraph, never read by the product)
```

**Neo4j** stores labels `Paper`, `Method`, `Entity`, `Claim`, `HypothesisSeed` with `SUPPORTS` / `CONTRADICTS` / `USES` / `EVALUATES_ON` / `DERIVES_FROM` relationships.

**Indexing to hit the NFR targets:**
- DAG < 100 ms @ 10k nodes: adjacency list (`parent_id`) + index on `(program_id, parent_id)`; add a **closure table** (or `ltree` materialized path) for O(depth) subtree/ancestor queries instead of recursive CTE scans.
- Domain graph < 200 ms @ 1M nodes: Neo4j composite indexes on entity natural keys + bounded-depth traversals in the MCP query templates.

---

## 9. Observability & evaluation (LangSmith)

Tracing is automatic for every graph/subgraph run via env config (`LANGSMITH_TRACING=true`). Each proposer/critic/evaluator invocation is a trace; `runs.langsmith_trace_id` links it to the DAG.

**Three evaluation jobs**, run as LangSmith datasets + evaluators:

1. **Critic reliability eval** — a curated dataset of gamed/leaky/regressed patches with known-bad labels; the metric is the Critic's catch rate. This is what justifies the SRS's two-agent reliability claim *before* expanding the swarm.
2. **Proposer quality eval** — held-out hypotheses scored on whether proposals improve the primary metric.
3. **Regression + cost CI** — the nanochat demo program runs in CI; LangSmith captures per-run token/$ which feeds:
   - **budget enforcement** at runtime (`budgets.spent_usd` updated from trace cost), and
   - a **CI gate** that fails the build if demo cost drifts above the < $20 target (SRS Risk: *LLM spend creep*).

LangSmith self-hosts via its Helm chart and reports from the same Agent Server, so the whole observability stack stays inside the deployment (OSS / single-tenant constraint).

---

## 10. API surface

**Control plane (FastAPI) — product/control:**

```
POST /programs                 # import research.yaml, kick off the loop
GET  /programs/{id}/dag        # DAG (paged/aggregated for UI)
GET  /hypotheses/{id}          # node detail (+ trace link)
GET  /runs/{id}                # run detail, score vector, artifacts
GET  /approvals?status=pending
POST /approvals/{id}/decide    # approve/deny → resumes the parked thread
GET  /programs/{id}/stream     # SSE: live traces/events from Redis
POST /runs/{id}/replay         # re-execute a kept run deterministically
```

**Reasoning plane** is reached through the **LangGraph Server's** own REST + SSE / Agent Protocol (threads, runs, interrupts, `Command(resume=…)`). FastAPI is the only thing that talks to it directly; the UI never calls the runtime.

---

## 11. Non-functional realization

| Requirement | How |
| --- | --- |
| Crash recovery | LangGraph durable execution + Postgres checkpointer; idempotent durable writes keyed on proposal hash. A killed orchestrator resumes every parked thread on restart. |
| Replayable kept runs | Artifacts + event log + context snapshot ref stored per run; replay re-runs against the same inputs (determinism mode optional — see §13). |
| Neo4j degradation | pgvector-only context-pack fallback with `degraded` flag; loop continues. |
| Secrets isolation | Creds live in the MCP server / backends; agents get tools, never secrets or connection strings. |
| Sandbox isolation | Agent sandbox (small code tools) is separate from GPU backends (real jobs); neither can reach the other's credentials. |
| Portability | `docker compose up` brings up Postgres+pgvector, Neo4j CE, Redis, MinIO, the MCP server, LangGraph Server, FastAPI, and (Phase 2) LangSmith. Runtime/backend layers are swappable behind their interfaces. |

---

## 12. Phased delivery (mapped to components)

| Phase | Ships |
| --- | --- |
| **1 — CLI-first core** | LangGraph research-loop graph (proposer+evaluator), Postgres system of record + checkpointer (separate schemas), `LocalBackend`, minimal MCP server (read tools), CLI (`crucible import`, `crucible run`), nanochat example. LangSmith tracing on from day one. |
| **2 — Independence + context + UI** | Critic subgraph on an independent provider, Neo4j context engine + Context Broker + pgvector, `ModalBackend`, web UI (DAG, trace panel, evidence graph, approvals), richer evaluator scoring, LangSmith eval datasets + cost CI. |
| **3 — Launch readiness** | `ColabBackend`, docs, comparison demo, contributor guide, replay/determinism polish. |
| **Deferred** | Domain packs, K8s/SLURM, hosted SaaS, active-learning policies, >2-agent swarm. |

---

## 13. Trade-offs & what I'd revisit

- **Whole loop as one graph vs. FastAPI owning the loop.** I chose loop-as-graph (matches "LangGraph for orchestration" and gives free durability/HITL). *Revisit if* you need many concurrent programs with heavy cross-program scheduling — at that point a thin external scheduler calling per-expansion graphs scales more cleanly.
- **Checkpointer = Postgres.** Simple, one fewer service. *Revisit* (Redis/Mongo checkpoint) only if checkpoint write volume becomes a hotspot; unlikely at single-tenant scale.
- **Neo4j Community Edition.** No clustering/HA/hot-backup. This is why graceful degradation is mandatory, not optional. *Revisit* (Enterprise or a different graph store) only if HA becomes a real requirement — out of scope for v2.
- **State holds ids, not content.** Keeps checkpoints tiny and truth in the DB, at the cost of extra fetches per node. Right trade-off given the "session ≠ research state" rule.
- **Structured output everywhere.** Slightly more brittle to model quirks than free-text, but it's the price of a stable, auditable boundary. Validation failures route to a `revise` path rather than crashing the loop.

**Recommendations on the remaining SRS open questions:**
- *Fallback reasoning adapter?* Not needed as a separate runtime — the LangGraph + `init_chat_model` boundary already isolates you from any single provider/runtime.
- *Determinism mode mandatory for replay-critical programs?* Make it **opt-in per program** (seed pinning + pinned model versions). Mandatory determinism fights exploration; replay-critical programs flip it on.
- *Auto-confirmation aggressiveness for quarantined hypotheses?* Conservative default: one confirmation run, only if budget headroom > a configurable threshold; otherwise leave quarantined for human triage.
- *5k-node UI cap?* Acceptable if rendering is **server-aggregated + virtualized** (collapse rejected subtrees, lazy-expand). Raw client-side rendering of 5k nodes is not acceptable; design the DAG endpoint to page/aggregate.

---

## 14. Suggested repository layout (OSS)

```
crucible/
├─ langgraph.json                 # graph + subgraph registration for LangGraph Server
├─ docker-compose.yml             # postgres+pgvector, neo4j, redis, minio, mcp, lg-server, api
├─ crucible/
│  ├─ graph/                      # research-loop graph + nodes
│  │  ├─ research_loop.py
│  │  ├─ proposer.py              # proposer subgraph
│  │  ├─ critic.py                # critic subgraph
│  │  └─ state.py
│  ├─ api/                        # FastAPI control plane
│  ├─ mcp_server/                 # context + DAG tools (langchain-mcp-adapters)
│  ├─ context/                    # Context Broker, ingestion, entity resolution
│  ├─ backends/                   # local.py, modal.py, colab.py (Backend protocol)
│  ├─ store/                      # Postgres models, Neo4j client, pgvector, MinIO
│  └─ evals/                      # LangSmith datasets + evaluators
├─ examples/nanochat/             # the demo program (research.yaml)
└─ docs/                          # SRS, this DESIGN.md, contributor guide
```

---

*End of Crucible v2 system design.*
