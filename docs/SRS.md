# Crucible v2 — Software Requirements Specification

> **Version:** 2.1 (refined) · **Date:** June 2026 · **Status:** Draft for build
> **Supersedes:** `crucible_v2_srs (2).html` (SRS v2.0, May 2026).
> Refinements per [`REFINEMENT.md`](./REFINEMENT.md) are incorporated.
> Implementation companion: [`SYSTEM_DESIGN.md`](./SYSTEM_DESIGN.md).

---

## 1. Introduction

### 1.1 Purpose

This document specifies **what** Crucible v2 must do and the constraints it must
satisfy. It is the contract between the product intent and the implementation
described in the System Design. It is written to be testable: every functional
requirement has acceptance criteria, and every non-functional requirement has a
measurable target.

### 1.2 Product overview

Crucible v2 is a **single-tenant, self-hostable, open-source research operating
system**. It runs autonomous, reproducible **research programs**. A program grows
a durable **hypothesis DAG** through a **Proposer/Critic** loop under
**beam-bounded search**, evaluates each hypothesis on multiple metrics, gates
expensive or risky actions behind **human approval**, and exposes inspectable
views for **DAG, evidence graph, traces, replay, approvals, and budgets**.

The defining principle is **"the agent session is not the research state."** Agent
invocations are disposable workers. Durable truth lives in Postgres, Neo4j, object
storage, and replayable event metadata.

### 1.3 Program types (scope unification)

One engine serves three use cases via a program type (see REFINEMENT R0):

- `literature_synthesis` — autonomous deep research + RAG over a corpus/web,
  producing cited claims and report sections. **Ships first.**
- `ml_experiment` — autonomous ML autoresearch, producing patch diffs, training
  runs, and benchmark scores.

The DAG, Critic, approvals, budgets, provenance, replay, and UI are common to all
types; only the *expand* and *run* steps specialize.

### 1.4 Definitions

| Term | Meaning |
| --- | --- |
| **Program** | A declared research effort (`research.yaml`): goal, metrics, budget, beam, sources, backend, type. |
| **Hypothesis** | A durable DAG node: a proposed direction (a claim to investigate or a patch to try). Never deleted. |
| **Run** | An execution attempt for a hypothesis (synthesis or experiment). |
| **Claim** | An extracted or empirical statement with provenance and optional embedding. |
| **Context pack** | A compact, per-hypothesis bundle of relevant claims/methods/contradictions/prior runs built by the MCP server. |
| **Approval** | A human decision record gating an escalated or over-budget action. |
| **System of record** | Postgres `crucible` schema + Neo4j + object store — the permanent truth. |
| **Checkpoint** | LangGraph per-thread execution snapshot (schema `lg_checkpoints`) — disposable recovery state only. |

### 1.5 Stakeholders

Self-hosting researchers/engineers (primary users), OSS contributors, and
operators running a single-tenant deployment.

---

## 2. Goals and scope

### 2.1 Goals

1. Reproduce the autoresearch reliability primitive on a modern, open deployment
   stack (LangGraph / LangChain / pluggable tracer).
2. Store the hypothesis DAG as **durable data**, not agent-thread history.
3. Add a **Critic** agent on an **independent model provider**.
4. Expose a real **trust layer**: DAG view, evidence graph, traces, replay,
   approvals, budgets.
5. Keep **execution pluggable** (Local → Container → optional Modal/Colab) and the
   **model/runtime boundary thin** so providers swap by config.
6. Run **fully self-hosted** via `docker compose up`, in a `lite` (one-service) or
   `full` (production-grade) profile.

### 2.2 Non-goals (v2)

- No "fully autonomous scientist" claim.
- No bio/chem/quant domain packs.
- No multi-tenant SaaS or hosted product.
- No agent swarm beyond two agents until two-agent reliability is proven by evals.
- No custom inline-Python tools in the agent layer (tools are the MCP surface).

### 2.3 Constraints

- **OSS, single-tenant, self-hostable.** No proprietary hard dependency on the
  default path (tracing, embeddings, and backends all have OSS defaults).
- **Neo4j Community Edition** in the `full` profile (single instance, no HA, no
  Enterprise-only NODE KEY / existence constraints → app enforces required
  properties). The `lite` profile uses Apache AGE inside Postgres.
- **Secrets never enter agent prompts.** Agents receive tools, never credentials,
  connection strings, or raw SQL/Cypher.
- **PostgreSQL 15+** locally (Supabase CLI rejects `major_version = 16`); 16+ in
  hosted. Schema relies only on features available in 15 (incl.
  `UNIQUE NULLS NOT DISTINCT`).

---

## 3. Functional requirements

### FR-1 — Research programs

- **FR-1.1** A program is declared in `research.yaml` with: `name`, `type`
  (`literature_synthesis` | `ml_experiment`), `goal`, `metrics`, `budget_usd`,
  `beam_width` (min/max for adaptive beam), `backend`, and `sources` (papers/URLs
  to ingest).
- **FR-1.2** `POST /programs` validates the spec and, on success, writes a
  `programs` row and an initialized `budgets` row, and optionally a root
  hypothesis (depth 0).
- **FR-1.3** Invalid specs return **field-specific** validation errors (no program
  is created).
- **FR-1.4** `crucible import <spec>` converts an autoresearch-style spec into the
  program structure.

**Acceptance:** invalid spec → field errors, no rows; valid spec → `programs` +
`budgets` rows; root hypothesis (if requested) has `depth = 0` and a closure row.

### FR-2 — Hypothesis DAG

- **FR-2.1** Each accepted proposal becomes a durable hypothesis node with
  `program_id`, `parent_id`, `depth`, `status`, `proposal_hash`, `compact_summary`,
  `patch_diff_ref` (nullable), and context refs.
- **FR-2.2** Nodes are **never deleted**; rejected and quarantined paths remain
  inspectable.
- **FR-2.3** Durable writes are **idempotent** on `(program_id, parent_id,
  proposal_hash)` so a replayed/resumed node upserts, never duplicates.
- **FR-2.4** A novelty gate skips/merges near-duplicate proposals before they
  consume a beam slot (REFINEMENT R3.3).
- **FR-2.5** Ancestor/subtree queries are served from the closure table, not
  recursive CTEs.

**Acceptance:** root + child inserts populate `hypothesis_closure`; duplicate
`(program_id, parent_id, proposal_hash)` is idempotent/deterministic-conflict;
subtree query returns correct depth-scoped descendants.

### FR-3 — Reasoning loop (Proposer / Critic)

- **FR-3.1** The Proposer consumes a context pack and returns a **schema-validated**
  `PatchProposal` (statement, rationale, expected effect, patch/answer ref, domain
  refs).
- **FR-3.2** The Critic runs on a **different model family by default** and returns
  a schema-validated `CriticVerdict` (verdict, gaming/leakage/regression risk,
  contradictions, notes).
- **FR-3.3** Proposals are conditioned on **kept** hypotheses of the same program
  (success memory, REFINEMENT R3.2).
- **FR-3.4** Beam width is **adaptive** to budget headroom and recent yield, within
  configured bounds.
- **FR-3.5** Graph state carries **ids and counters only** — never full research
  content.

**Acceptance:** proposer/critic outputs validate against Pydantic schemas;
validation failure routes to a `revise` path (no loop crash); critic model is
independently configurable.

### FR-4 — Execution and runs

- **FR-4.1** Backends implement one `Backend` protocol: `submit`, `status`,
  `fetch_artifacts`, `stream_events`. `LocalBackend` and `ContainerBackend` are
  built-in; Modal/Colab are optional plugins.
- **FR-4.2** A run progresses through `queued → running → succeeded|failed|
  cancelled`, recorded in `runs`.
- **FR-4.3** Live events stream to the UI over `/programs/{id}/stream`; they are
  then persisted to `crucible.events` for replay.
- **FR-4.4** Artifacts are immutable, written under the documented object-key
  layout; rows store only `_ref`s.
- **FR-4.5** Long jobs do not block the graph: the node dispatches, the thread
  parks on `interrupt()`, and the control plane resumes on completion.

**Acceptance:** local job → `runs` row + streamed events + persisted events +
artifact refs; loss of the live stream after flush loses no replayable events.

### FR-5 — Evaluation

- **FR-5.1** The evaluator maps Critic + score outputs to one of `keep`, `reject`,
  `quarantine`, `escalate`.
- **FR-5.2** Scoring includes primary metric, secondary metrics, cost,
  reproducibility, novelty, and domain confidence.

**Acceptance:** each decision state is reachable and recorded on the run/hypothesis.

### FR-6 — Approvals and governance

- **FR-6.1** Escalated or over-budget actions create an `approvals` row
  (`status=pending`, `ttl`, `audit`) and **park** the graph on `interrupt()`.
- **FR-6.2** `POST /approvals/{id}/decide` resumes the parked thread with
  approve/deny and stamps the audit trail.
- **FR-6.3** TTL expiry **auto-denies** with a recorded reason (never silent).
- **FR-6.4** Approvals are never auto-granted from anything an agent or document
  "says."

**Acceptance:** approve/deny/expire all reachable; decision resumes the run; expiry
records an audit entry.

### FR-7 — Budgets and cost

- **FR-7.1** Each program has a hard `cap_usd`; spend is tracked from trace cost
  into `budgets.spent_usd`.
- **FR-7.2** Approaching the cap triggers a soft-warning band; exceeding it routes
  to approval or halts the program.
- **FR-7.3** Live budget burn-down is exposed to the UI/CLI.

**Acceptance:** spend accrues from runs; over-cap action escalates or halts; UI
shows spent vs. cap live.

### FR-8 — Context engine

- **FR-8.1** A Context Broker ingests papers/URLs and kept-run outputs, extracts
  entities/methods/claims/relations, writes the Neo4j domain graph and Postgres
  `claims`, and generates embeddings.
- **FR-8.2** `get_context_pack(hypothesis_id)` returns a compact pack via **hybrid
  retrieval** (structural + lexical + semantic, reranked).
- **FR-8.3** If Neo4j is unavailable, the pack falls back to lexical+semantic from
  Postgres and is flagged `degraded=true`; the loop continues.
- **FR-8.4** Context packs are cached and invalidated on new program claims.

**Acceptance:** ingesting a sample paper creates Paper/Method/Entity/Claim nodes,
mirrors claims to Postgres, stores embeddings; pack includes relevant claims +
contradictions + prior run summaries + degradation flag.

### FR-9 — MCP tool boundary

- **FR-9.1** Agents access data **only** through the MCP server, which holds
  credentials and exposes **parameterized, read-mostly** tools:
  `get_context_pack`, `query_domain_graph`, `search_claims`, `get_dag_node`,
  `get_run_summary`, and a **staged, gated** `record_claim`.
- **FR-9.2** No tool accepts raw SQL or raw Cypher from model input.
- **FR-9.3** Writes are staged and require the normal approval path before becoming
  durable truth.

**Acceptance:** no raw-query path exists; agents receive no connection strings;
`record_claim` writes only to staging.

### FR-10 — Replay and provenance

- **FR-10.1** A kept run can be replayed deterministically from immutable artifact,
  event-log, and context-snapshot refs.
- **FR-10.2** From any DAG node the user can reach its run, claims, artifacts, and
  full execution trace, and back.
- **FR-10.3** Determinism mode (seed + pinned model versions) is **opt-in per
  program**.

**Acceptance:** replay of a kept run produces a linked replay run; node↔trace
round-trip works via the stored trace id.

### FR-11 — Product surfaces

- **FR-11.1 (CLI, Phase 1):** `import`, `run`, `status`, `approvals`, `replay`,
  `quickstart`, with live cost output. CLI talks to FastAPI only.
- **FR-11.2 (Web UI, Phase 2):** program/DAG view, hypothesis/run detail, approvals
  queue, evidence graph, live trace+cost panel. UI talks to FastAPI only — never to
  LangGraph Server, Neo4j, Redis, or Postgres directly.
- **FR-11.3** The DAG view is server-aggregated, paged, and virtualized; rejected
  subtrees collapse and lazy-expand.

**Acceptance:** user can create/select a program and inspect its DAG; large trees
render without raw client-side dumping; approvals can be decided from the UI; trace
panel updates live.

---

## 4. Data model (authoritative)

Postgres is the operational source of truth; Neo4j augments it. Columns shown are
the contract; full DDL lives in `supabase/schemas/`.

```sql
-- schema: crucible (system of record)
programs(id, name, type, version, spec_yaml, neo4j_graph_id, owner, created_at, updated_at)
hypotheses(id, program_id, parent_id, depth, status, proposal_hash,
           patch_diff_ref, compact_summary,
           lg_thread_id, proposer_run_id, neo4j_context_ref, created_at, updated_at)
hypothesis_closure(ancestor_id, descendant_id, depth, created_at)   -- O(depth) subtree/ancestor
runs(id, hypothesis_id, backend, status, started_at, ended_at,
     score_vector_json, critic_verdict_json,
     artifacts_ref, event_log_ref, trace_id, neo4j_context_snapshot_ref, created_at, updated_at)
claims(id, hypothesis_id, run_id, statement, source_artifact_ref,
       confidence, neo4j_claim_id, embedding vector(N), created_at)
approvals(id, run_id, kind, status, ttl, requested_at, decided_at, decided_by, audit jsonb)
budgets(id, program_id, cap_usd, spent_usd, updated_at)
events(id, run_id, ts, kind, payload jsonb)

-- schema: lg_checkpoints  (owned by LangGraph; never read as product truth)
```

**Enums:** `hypothesis_status(proposed|running|kept|rejected|quarantined|escalated)`,
`run_status(queued|running|succeeded|failed|cancelled)`,
`approval_status(pending|approved|denied|expired)`.

**Idempotency:** `hypotheses` UNIQUE `NULLS NOT DISTINCT (program_id, parent_id,
proposal_hash)`.

**Neo4j:** labels `Paper, Method, Entity, Claim, HypothesisSeed`; relationships
`USES, EVALUATES_ON, SUPPORTS, CONTRADICTS, DERIVES_FROM`. `Claim.id` mirrors
`claims.neo4j_claim_id`.

> **Refinement note:** `programs.type` is added (R0), and the trace linkage column
> is named `trace_id` (provider-neutral) rather than `langsmith_trace_id`, since
> the tracer is pluggable (R1.2). Existing migrations may keep the legacy column
> name with a view/alias until the next migration.

---

## 5. External integrations

| Area | Integrations |
| --- | --- |
| Reasoning | LangGraph Server (REST + SSE / Agent Protocol); `langchain-mcp-adapters`; model routing across OpenAI / Anthropic / Google / local (Ollama) via `init_chat_model`. |
| Observability | Pluggable `Tracer`: **Langfuse** or **OpenTelemetry** (OSS default), LangSmith optional. |
| Execution | LocalBackend, ContainerBackend (Docker/SSH); optional Modal / Colab plugins. |
| Storage | Postgres 16 + pgvector; Neo4j 5 CE *(full)* or Apache AGE *(lite)*; Redis *(full)* or `LISTEN/NOTIFY` *(lite)*; MinIO/S3 *(full)* or local FS *(lite)*. |
| Embeddings | Local `bge-small` / Ollama (default) or API embeddings (opt-in). |

---

## 6. Non-functional requirements

| ID | Requirement | Target / measure |
| --- | --- | --- |
| NFR-1 Performance (DAG) | DAG queries fast at scale | **< 100 ms** for 10k-node trees (closure-table reads). |
| NFR-2 Performance (graph) | Domain-graph queries fast at scale | **< 200 ms** for 1M-node graphs (indexed, bounded-depth). |
| NFR-3 Cost | Overnight program spend | **< $20** (LLM < $10, GPU $5–8); CI cost guard on the demo. |
| NFR-4 Reliability | Crash recovery | Orchestrator restart resumes every parked thread; durable-write-before-complete + idempotent upserts. |
| NFR-5 Reliability | Graph degradation | Neo4j down → pgvector/lexical context pack with `degraded=true`; program continues. |
| NFR-6 Security | Secret isolation | No secret/connection string/raw query ever reaches an agent prompt; creds live in MCP/backends/API. |
| NFR-7 Security | Sandbox isolation | Agent sandbox (small code tools) is isolated from GPU/exec backends; neither reaches the other's creds. |
| NFR-8 Portability | Self-host | `docker compose up` (lite: 1 service; full: 4). Runtime/backend/tracer/embeddings swappable behind interfaces. |
| NFR-9 Replay | Determinism | Opt-in per program; replay-critical programs reproduce from immutable refs. |
| NFR-10 UI | Large DAG render | Server-aggregated + virtualized; no raw render of > configured node cap; WCAG 2.1 AA. |
| NFR-11 Observability | Traceability | Every proposer/critic/evaluator invocation traced; `runs.trace_id` links DAG↔trace. |

---

## 7. Cost model

| Item | Target |
| --- | --- |
| Proposer LLM | < $5 |
| Critic LLM | < $3 |
| Summaries + context queries | < $2 |
| GPU (ml_experiment only) | $5–8 |
| **Total overnight** | **< $20** |

Controls: beam-bounded + adaptive search, context-pack caching, novelty/dedup gate,
local embeddings, and a CI cost guard that fails the build on demo-cost drift.

---

## 8. Phased delivery

| Phase | Ships |
| --- | --- |
| **1 — CLI-first core** | LangGraph research-loop (proposer + evaluator), Postgres system of record + checkpointer (separate schemas), Local/Container backends, minimal MCP read tools, CLI, `literature_synthesis` demo. Tracing on from day one. |
| **2 — Independence + context + UI** | Critic on an independent provider, Neo4j/AGE context engine + Broker + pgvector hybrid retrieval, web UI (DAG, trace+cost panel, evidence graph, approvals), richer evaluator, eval datasets + cost CI, `ml_experiment` + ModalBackend (optional). |
| **3 — Launch readiness** | Colab backend (optional), docs, comparison demo, contributor guide, replay/determinism polish, `lite`/`full` profile hardening. |
| **Deferred** | Domain packs, K8s/SLURM, hosted SaaS, active-learning policies, > 2-agent swarm. |

---

## 9. Risks and mitigations

| Risk | Assessment | Mitigation |
| --- | --- | --- |
| LLM spend creep | Med / High | Hard budgets, adaptive beam, caching, dedup, CI cost guard. |
| Operational weight of 4 stores | Med / Med | `lite` single-service profile (AGE + LISTEN/NOTIFY + FS); `full` for scale. |
| Neo4j single-instance (no HA) | Med / Med | Mandatory graceful degradation; Dockerized; AGE fallback in `lite`. |
| UI scope creep | High / Med | CLI-first Phase 1; UI in Phase 2 behind server-aggregated DAG. |
| Provider/runtime churn | Low / Med | `init_chat_model` + LangGraph boundary; pinned versions. |
| Critic reliability unproven | Med / High | Labeled eval dataset + catch-rate gate before any agent-count expansion. |

---

## 10. Open questions — resolved

See [`REFINEMENT.md` §7](./REFINEMENT.md). All five v2.0 open questions now have
decisions (fallback adapter: no; determinism: opt-in; auto-confirm: conservative;
extraction: spaCy+LLM; 5k-node cap: yes, with aggregation+virtualization).

---

*End of Crucible v2 SRS (refined v2.1).*
