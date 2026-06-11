# Crucible v2 — Project Refinement

> A focused, opinionated pass over the existing Crucible v2 / Autoresearch Atlas
> design through five lenses: **Feasibility, UX, Speed, Intelligence, UI**.
> This document does not replace the SRS or System Design; it records the
> decisions those documents now incorporate, and the reasoning behind them.
>
> Companion documents: [`SRS.md`](./SRS.md), [`SYSTEM_DESIGN.md`](./SYSTEM_DESIGN.md),
> [`CODE_GUIDELINES.md`](./CODE_GUIDELINES.md), [`sprints/OVERVIEW.md`](./sprints/OVERVIEW.md).

---

## 0. What Crucible v2 is — restated and widened

Crucible v2 is a **single-tenant, self-hostable, open-source research operating
system**. It runs autonomous, reproducible *research programs*: it grows a
durable hypothesis DAG via a Proposer/Critic loop under beam-bounded search,
scores each hypothesis on multiple metrics, gates expensive or risky work behind
human approval, and exposes DAG / evidence-graph / trace / replay views.

The existing v1→v2 lineage framed every program as an **ML experiment** (patch
diffs, GPU training, benchmark eval). The single most valuable refinement in this
pass widens that framing without breaking it.

### Refinement R0 — Generalize via `ProgramType` (the unification)

The product is best understood as the **union of three things the same engine can
do**:

1. An **autonomous deep-research agent** — take a question, plan, retrieve from
   web + corpora, and produce a cited synthesis.
2. A **RAG knowledge workspace** — ingest your own documents/papers into durable
   domain memory and reason over them with provenance.
3. A **multi-agent research platform** — a Proposer/Critic (A2A) loop that
   explores a space of hypotheses under governance.

These are not three products. They are **one DAG + one Critic + one approval +
one provenance machine** with a **pluggable program type and backend**:

```
ProgramType = literature_synthesis | ml_experiment | (future: data_analysis, ...)
```

| Program type | "Hypothesis" means | Backend does | Output artifact |
| --- | --- | --- | --- |
| `literature_synthesis` | a claim/answer to investigate | retrieve + read + synthesize (no GPU) | cited report section + claims into the graph |
| `ml_experiment` | a code patch to try | train/eval on Local/Modal/Colab | score vector + checkpoints + claims |

The Context Broker, Neo4j domain graph, pgvector recall, Critic, approvals,
budgets, replay, and DAG UI are **identical** across types. Only the *expand* and
*run_experiment* nodes specialize. This is what makes the "deep research +
RAG + multi-agent" combination coherent rather than three half-products, and it
sequences cleanly: **`literature_synthesis` ships first** (no GPU dependency,
broadest audience, fastest to a usable demo), `ml_experiment` follows.

This refinement is reflected in the SRS (FR-1, data model `programs.type`) and
the System Design (§Execution backends).

---

## 1. Feasibility

The original design is sound but assumes infrastructure that is heavy for the
"self-host on a laptop" promise. Four refinements lower the barrier without
abandoning the production-grade path.

### R1.1 — Two Docker Compose profiles: `lite` and `full`

The accepted ADR runs four datastores (Postgres+pgvector, Neo4j, Redis, MinIO).
That is correct for scale, but it is a steep first run for an OSS contributor.
Ship **two profiles from one compose file**:

| Concern | `full` profile (production-grade) | `lite` profile (laptop / first run) |
| --- | --- | --- |
| Relational truth + vectors | Postgres 16 + pgvector | Postgres 16 + pgvector |
| Domain graph | Neo4j 5 CE | **Apache AGE** in the same Postgres (Option B in ADR-0001) |
| Live streams | Redis Streams | **Postgres `LISTEN/NOTIFY`** |
| Artifacts | MinIO / S3 | **local filesystem volume** |
| Services to run | 4 | **1** |

Both profiles sit behind the **same MCP tool API and the same repository
interfaces**, so application code does not branch — only the wiring does. ADR-0001
already names Apache AGE as the sanctioned fallback "behind the existing MCP query
templates — agents wouldn't notice." This refinement promotes that from a
"revisit later" note to a **shipped `lite` profile**, which is the single biggest
adoption lever for an OSS project.

### R1.2 — Make observability self-hostable by default (Langfuse/OTel, not only LangSmith)

The System Design assumes **LangSmith** for tracing/evals, self-hosted via Helm.
A Helm chart contradicts "runs on a laptop with `docker compose up`." Refinement:

- Define a thin **`Tracer` boundary** (the design already calls for a reasoning
  adapter boundary — extend it to observability).
- Default self-host tracer: **Langfuse** (OSS, single container, Postgres-backed)
  or raw **OpenTelemetry** to any OTLP collector.
- LangSmith becomes an **optional** adapter for teams that want it.

Net effect: tracing, cost capture, and the eval harness all work in a pure-OSS
deployment with no proprietary dependency. (Resolves the unstated tension in
System Design §9.)

### R1.3 — Demote GPU backends to optional plugins; add a generic backend

Modal and Colab are not available to most self-hosters and add credentials/SaaS
coupling. Refinement to the backend phasing:

- **Tier 1 (always present):** `LocalBackend` (subprocess/container on the host).
- **Tier 1.5 (new, recommended default for real work):** `ContainerBackend` —
  run a job in a Docker container or over SSH to a box the user already owns. No
  third-party account required.
- **Tier 2 (optional plugins):** `ModalBackend`, `ColabBackend`, behind the same
  `Backend` protocol and discovered via entry points so they are not core deps.

This keeps the GPU story pluggable (a stated goal) while making the **default path
fully self-contained**.

### R1.4 — Pin the LLM/runtime boundary, drop "Deep Agents"

Already decided in `DESIGN.md`: build on **raw LangGraph 1.x + `init_chat_model`**
rather than the Deep Agents beta. This refinement endorses and locks it: it
removes the "Deep Agents beta churn" risk entirely and makes provider swaps a
config change. The SRS open question *"ship a parallel fallback reasoning
adapter?"* is therefore **closed: not needed** — the `init_chat_model` seam is the
adapter.

---

## 2. Speed

Performance targets are good (DAG < 100 ms @ 10k nodes; domain graph < 200 ms @
1M nodes; overnight cost < $20). The refinements below make them reliably hit-able
and add front-end responsiveness.

### R2.1 — Indexing specifics

- **DAG:** keep the adjacency list + `hypothesis_closure` trigger (already built).
  Add a covering index `(program_id, parent_id, status, depth)` for the common UI
  query, and serve subtree/ancestor reads **only** from the closure table — never
  a recursive CTE on the hot path.
- **pgvector:** use an **HNSW** index (`vector_cosine_ops`) on `claims.embedding`,
  not IVFFlat — better recall/latency for the single-tenant data sizes here, and
  no training step. Set `ef_search` per query for the latency/recall trade.
- **Neo4j:** composite + full-text indexes already specified; enforce
  **bounded-depth** traversal in every MCP template (no unbounded `*` paths).

### R2.2 — Context-pack caching

Building a context pack hits Neo4j + pgvector on every proposer call. Cache it:

- Key: `(hypothesis_id, domain_graph_version)`.
- Store: Redis (`full`) / Postgres unlogged table (`lite`), short TTL.
- Invalidate when the Context Broker writes new claims for the program.

This removes the dominant per-expansion latency and cost in deep, wide beams.

### R2.3 — Local/cheap embeddings by default

For self-host speed and the cost target, default embeddings to a **local model**
(e.g. `bge-small-en-v1.5` via `fastembed`, or an Ollama embedding model) with an
**API embedding adapter** (OpenAI `text-embedding-3-small`, etc.) as opt-in. The
1536-dim column already in the schema accommodates either via a configured
dimension. Embeddings are batched and written by the Broker, never inline in a
graph node.

### R2.4 — Streaming and UI responsiveness

- Live events over **SSE** from Redis (`full`) / `LISTEN/NOTIFY` (`lite`); both
  behind one `/programs/{id}/stream` endpoint.
- DAG endpoint is **server-aggregated and cursor-paged** (see R5.1) so the client
  never blocks on a 10k-node payload.
- Token/cost meter is computed server-side from trace cost and streamed, so the
  budget burn-down is live without client polling.

---

## 3. Intelligence

The two-agent (Proposer/Critic) core is the right reliability primitive. These
refinements raise answer quality and reduce wasted spend.

### R3.1 — Hybrid retrieval for context packs (not vector-only)

Vector recall alone misses exact-term and structural matches. The context pack
should combine, then rerank:

1. **Structural** signal from Neo4j (claims/contradictions reachable from the
   hypothesis seed, bounded depth).
2. **Lexical** signal from Neo4j full-text (`claim_fulltext`) / Postgres FTS.
3. **Semantic** signal from pgvector (HNSW).
4. A lightweight **reranker** (cross-encoder or LLM-as-reranker over the top-k
   union) producing the final compact pack.

Degradation (R from the original design) still holds: if Neo4j is down, fall back
to lexical+semantic from Postgres with `degraded=true`.

### R3.2 — Success memory conditions the Proposer

Condition each proposal on **kept** hypotheses from the same program (few-shot
from `status='kept'` summaries). The DAG already records outcomes; feeding the
winners back closes the learning loop the SRS gestures at ("later proposals are
conditioned on accumulated evidence").

### R3.3 — Novelty / dedup gate before expansion

Before spending a beam slot, embed the candidate hypothesis statement and check
semantic similarity against existing siblings/ancestors. If it is a near-duplicate
of an already-explored node, **skip or merge** rather than re-running it. This
directly protects the cost target and widens *effective* exploration for the same
budget.

### R3.4 — Adaptive beam width

Make `beam_width` a function of **budget headroom and recent yield**: widen when
budget is ample and kept-rate is high, narrow as the cap approaches. Bounded by a
configured min/max. Keeps spend in the target class while exploring as widely as
the budget safely allows.

### R3.5 — Calibrated Critic, justified by evals

The Critic's value is only real if measured. The eval harness (System Design §9)
must ship a **labeled dataset of gamed/leaky/regressed** proposals and report the
Critic's catch rate **before** any expansion of the agent count past two. Verdict
fields (`gaming_risk`, `leakage_risk`, `regression_risk`) should be **calibrated**
against this set, not raw model scores.

---

## 4. UX

CLI-first for Phase 1, web UI in Phase 2 — correct. Refinements make each surface
pleasant and trustworthy.

### R4.1 — A first-class CLI

`crucible import <spec>`, `crucible run <program>`, `crucible status <program>`,
`crucible approvals`, `crucible replay <run>`. Rich, streaming output with a live
cost/budget line. The CLI talks to FastAPI only (same boundary as the UI). A clean
`crucible quickstart` runs the bundled `nanochat` / `lit-synthesis` example
end-to-end from a clean clone.

### R4.2 — Trust-forward approvals

The approval queue is the product's trust surface. It must show: what is being
approved and **why it escalated**, the **cost delta** vs. budget, a **TTL
countdown**, and the full **audit trail** after a decision. Keyboard-driven
approve/deny. TTL expiry auto-denies with a recorded reason (never silent).

### R4.3 — Live cost transparency

Every running program shows a **budget burn-down**: spent vs. cap, projected
completion cost, and a soft-warning band before the hard stop. No surprise spend
is the single biggest trust factor for an autonomous, paid-LLM tool.

### R4.4 — Provenance is one click away

From any DAG node: jump to its run, its claims, its source artifacts, and its full
execution trace — and back. The `langsmith_trace_id` / tracer link column on
`runs` exists precisely to make this round-trip instant.

### R4.5 — Honest empty/degraded states

When Neo4j is degraded, the UI says so (a `degraded` badge on affected packs)
rather than silently returning thinner context. Empty states explain the next
action (import a program, ingest papers, run the demo).

---

## 5. UI

### R5.1 — DAG visualization: aggregate + virtualize, never raw-render

Raw client-side rendering of a 5k–10k-node tree is not acceptable (SRS open
question). The DAG endpoint **aggregates and pages server-side**:

- Collapse rejected/quarantined subtrees into a single summary node, expandable on
  demand (lazy-load children by cursor).
- Stream node deltas; virtualize the canvas (render only what's in view).
- Render with **React Flow** for moderate trees and a WebGL graph renderer
  (e.g. Sigma.js / Cosmograph) when a subtree exceeds a node threshold.

The 5k-node cap is acceptable **only** with this strategy; it is now a requirement,
not a question.

### R5.2 — Design system: shadcn/ui + Tailwind on `packages/ui`

Standardize the web app on **Tailwind + shadcn/ui** components housed in the
existing `packages/ui` workspace, with design tokens (the SRS's teal `--primary:
#0d5c63`, IBM Plex type, light/dark) defined once and consumed everywhere. This
gives a coherent look with minimal custom CSS and keeps components shared between
`web` and `docs`. See `CODE_GUIDELINES.md` §Frontend.

### R5.3 — Four core views, in priority order

1. **Program / DAG view** (the home of a run).
2. **Hypothesis + Run detail** (score vector, critic verdict, artifacts, trace).
3. **Approvals queue** (the trust surface).
4. **Evidence graph** (Neo4j: claims with **contradiction edges highlighted** —
   the signal the Critic uses, made visible).

A live **trace panel** with the cost meter is present across views during a run.

### R5.4 — Accessibility and performance budgets

Target **WCAG 2.1 AA** (contrast, keyboard nav, focus order, reduced-motion for
the graph canvas). Set front-end performance budgets: interactive DAG under a
defined node count without dropped frames; SSE reconnect with backoff.

---

## 6. Net changes folded into the other documents

| Refinement | Lands in |
| --- | --- |
| R0 `ProgramType` unification | SRS FR-1, data model; System Design §Execution |
| R1.1 `lite`/`full` compose profiles | System Design §Deployment; Sprint 0 follow-up + Sprint 10 |
| R1.2 Pluggable tracer (Langfuse/OTel default) | System Design §Observability; Sprint 9 |
| R1.3 `ContainerBackend` + optional GPU plugins | System Design §Backends; Sprint 4 |
| R1.4 LangGraph + `init_chat_model` (no Deep Agents) | System Design §Stack (already) |
| R2.x indexing, caching, local embeddings, streaming | System Design §Data model, §Context; Sprints 2,4,6 |
| R3.x hybrid retrieval, success memory, dedup, adaptive beam, calibrated critic | System Design §Reasoning, §Context; Sprints 5,6,7,9 |
| R4.x CLI, approvals UX, cost transparency, provenance | Sprints 2,5,7,8 |
| R5.x DAG aggregation, shadcn design system, core views, a11y | System Design §Product plane; Sprint 8; `CODE_GUIDELINES.md` |

## 7. Decisions on the SRS open questions

| Open question | Decision |
| --- | --- |
| Parallel fallback reasoning adapter? | **No.** `init_chat_model` + the LangGraph boundary is the adapter (R1.4). |
| Determinism mandatory for replay-critical programs? | **Opt-in per program** (seed + pinned model versions); mandatory determinism fights exploration. |
| Auto-confirmation aggressiveness for quarantined hypotheses? | **Conservative:** one confirmation run only if budget headroom exceeds a configured threshold; else hold for human triage. |
| spaCy+LLM vs. dedicated extraction model? | **spaCy spans + LLM extraction pass** in v2, behind the Broker boundary so a dedicated model can replace it later. |
| 5k-node UI cap acceptable? | **Yes, only with R5.1** (server aggregation + virtualization). Now a requirement. |

---

*End of refinement.*
