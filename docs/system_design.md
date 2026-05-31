# Autoresearch Atlas System Design

## Source Documents

This design is synthesized from the documents currently in `docs/`:

- `crucible_v2_srs (2).html` - product requirements, scope, non-functional targets, and v2 delivery phases.
- `DESIGN.md` - LangGraph/LangChain/LangSmith implementation architecture.
- `ADR-0001-database-architecture.md` - accepted database strategy.
- `README.md` - datastore reference and state ownership boundaries.
- `neo4j.md` - domain graph labels, relationships, indexes, and access pattern.
- `redis-and-object-store.md` - live trace stream and artifact storage conventions.

## Product Goal

Autoresearch Atlas is the implementation home for Crucible v2: a single-tenant,
self-hostable research operating system that runs autonomous, reproducible
research programs. It grows a durable hypothesis DAG, dispatches experiment
runs, evaluates results, captures domain evidence, and gives users inspectable
views for provenance, traces, approvals, replay, and progress.

The central rule is that agent sessions are disposable workers. Durable research
truth lives in the system stores: Postgres, Neo4j, object storage, and replayable
event metadata. LangGraph checkpoints are crash-recovery state only.

## Architectural Principles

- Postgres is the system of record for programs, hypotheses, runs, claims,
  approvals, budgets, and events.
- LangGraph checkpoints live in a separate `lg_checkpoints` schema and are never
  read as product truth.
- Neo4j stores relationship-native domain memory and can degrade to pgvector
  recall if unavailable.
- Redis is live-streaming infrastructure only; persisted replay state belongs in
  Postgres and object storage.
- MinIO/S3 stores large immutable artifacts. Database rows store references,
  never blobs.
- Agents never receive database credentials or arbitrary SQL/Cypher access.
  Parameterized tools own all data access for reasoning.
- Expensive or risky actions require explicit approval records, not prompt-only
  decisions.

## System Planes

| Plane | Runtime | Primary Responsibility |
| --- | --- | --- |
| Product plane | Next.js web app | DAG view, trace panel, evidence graph, approvals, replay controls |
| Control plane | FastAPI | Product API, auth boundary, budgets, approvals, DAG queries, SSE fan-out, replay orchestration |
| Reasoning plane | LangGraph Server | Research-loop graph, proposer subgraph, critic subgraph, interrupts, checkpointing |
| MCP tool plane | MCP server | Safe parameterized access to DAG, claims, context packs, and graph queries |
| Execution plane | Backend adapters | Local, Modal, and Colab experiment execution |
| Context plane | Context Broker | Paper ingestion, claim extraction, entity resolution, embeddings, graph writes |
| State layer | Postgres, Neo4j, Redis, MinIO/S3 | Durable truth, domain graph, live streams, immutable artifacts |

## Data Ownership

### Postgres

Schema `crucible` owns durable product truth:

- `programs` stores imported research specs.
- `hypotheses` stores append-only DAG nodes.
- `hypothesis_closure` stores transitive DAG edges for fast ancestor/subtree
  queries.
- `runs` stores experiment attempts and trace/artifact references.
- `claims` stores empirical or extracted statements, optional embeddings, and
  Neo4j mirror ids.
- `approvals` stores human decisions with TTL and audit metadata.
- `budgets` stores cap/spend state.
- `events` stores replayable run event history flushed from Redis.

Schema `lg_checkpoints` is owned by LangGraph checkpointers. It is allowed to be
pruned or migrated by runtime tooling without losing research truth.

### Neo4j

Neo4j Community Edition stores domain memory:

- Nodes: `Paper`, `Method`, `Entity`, `Claim`, `HypothesisSeed`.
- Relationships: `USES`, `EVALUATES_ON`, `SUPPORTS`, `CONTRADICTS`,
  `DERIVES_FROM`.
- Only unique constraints and indexes are declared. Required properties are
  enforced by application code because Community Edition does not support
  Enterprise-only node-key or property-existence constraints.

### Redis

Redis carries live traces:

- `run:{run_id}:events` as a stream.
- `program:{program_id}:traces` as a pub/sub fan-out channel.
- `run:{run_id}:status` as optional quick status state.

After flush, durable replay reads from `crucible.events` and object storage, not
Redis.

### MinIO/S3

Artifacts are immutable and program-scoped:

- `programs/{program_id}/hypotheses/{hypothesis_id}/patch.diff`
- `programs/{program_id}/runs/{run_id}/`
- `programs/{program_id}/runs/{run_id}/events.jsonl`
- `programs/{program_id}/claims/{claim_id}/source.*`

Object keys are write-once. Replacement means writing a new key and updating the
database reference.

## Core Workflows

### Program Import

1. User submits `research.yaml` or an imported program spec.
2. FastAPI validates goals, metrics, budgets, backend policy, beam width, and
   source papers.
3. FastAPI writes `programs`, creates a budget row, and optionally creates an
   initial root hypothesis.
4. Context Broker queues source ingestion for papers and existing artifacts.
5. UI shows the program as created, even if domain ingestion is still running.

### Context Ingestion

1. Context Broker ingests papers and run outputs.
2. It extracts entities, methods, claims, and relationships.
3. It writes relational claims to Postgres and domain relationships to Neo4j.
4. It creates embeddings for semantic recall in pgvector.
5. If Neo4j is down, the broker records degraded state and leaves pgvector
   recall available.

### Hypothesis Expansion

1. LangGraph selects the current frontier under the beam width and budget.
2. Proposer subgraph requests a context pack through MCP tools.
3. Proposer returns a structured proposal, including statement, rationale,
   expected effect, patch diff, and domain references.
4. Patch diff is written to object storage.
5. Durable hypothesis row is written before the graph node completes.
6. Idempotency is enforced by `(program_id, parent_id, proposal_hash)`.

### Experiment Run

1. Control plane creates a `runs` row with status `queued` or `running`.
2. Execution backend dispatches local, Modal, or Colab work.
3. Redis streams live run events to the UI.
4. Artifacts are written to MinIO/S3.
5. Event persister flushes Redis stream entries into `crucible.events`.
6. Run status, score vector, critic verdict, and trace refs are persisted.

### Evaluation And Approval

1. Critic subgraph evaluates gaming, leakage, regression, contradictions, and
   result quality.
2. Evaluator maps outputs to `keep`, `reject`, `quarantine`, or `escalate`.
3. Escalations and over-budget actions create approval records.
4. LangGraph parks on interrupt until approval decision or TTL expiry.
5. FastAPI resumes the graph with an approved, denied, or expired result.

### Replay

1. User requests replay for a kept run.
2. Control plane loads run metadata, context snapshot refs, event log refs, and
   immutable artifacts.
3. Backend re-executes with replay-compatible settings.
4. New replay events are persisted and linked to the original run.
5. UI compares original and replay outputs.

## Public Interfaces

### FastAPI Control Plane

Initial API surface:

- `GET /health`
- `GET /health/dependencies`

Target product API:

- `POST /programs`
- `GET /programs/{id}`
- `GET /programs/{id}/dag`
- `GET /hypotheses/{id}`
- `GET /runs/{id}`
- `GET /approvals?status=pending`
- `POST /approvals/{id}/decide`
- `GET /programs/{id}/stream`
- `POST /runs/{id}/replay`

The UI calls FastAPI only. It does not call LangGraph Server, Neo4j, Redis, or
Postgres directly.

### MCP Tool Server

Target tool surface:

- `get_context_pack(hypothesis_id)`
- `query_domain_graph(structured_query)`
- `search_claims(text, k)`
- `get_dag_node(id)`
- `get_run_summary(id)`
- `record_claim(...)` as a staged, gated write path

Models receive tool results, not credentials or query languages.

### LangGraph Runtime

Target graph package:

- `langgraph.json`
- `research_loop` graph
- proposer subgraph
- critic subgraph
- Postgres checkpointer configured for `lg_checkpoints`

Graph state carries ids and counters. It does not carry full research content.

## Monorepo Design

The repo uses pnpm and Turbo for JavaScript/TypeScript work and uv for Python
services.

```text
apps/
  api/     FastAPI control-plane service managed by uv
  web/     Next.js product UI
  docs/    Next.js documentation app
packages/
  ui/
  eslint-config/
  typescript-config/
schema/
  neo4j/
supabase/
  schemas/
  migrations/
tools/
```

Python services expose `package.json` shims so Turbo can run a single root
workflow while uv remains the dependency manager for Python code.

## Reliability And Security

- Durable writes happen before graph-node completion.
- Replayed/resumed graph nodes must use idempotent writes.
- Every exposed Postgres table has RLS enabled, but the `crucible` schema is
  private and accessed through server-side credentials.
- Neo4j degradation returns pgvector-only context packs with `degraded=true`.
- Redis loss cannot lose research truth because Redis is not a system of record.
- Object storage writes are immutable and referenced by database rows.
- Secrets live in FastAPI, MCP, backend adapters, and deployment configuration,
  never in prompts or browser-exposed env vars.

## Current Implementation Status

Implemented in this repo:

- Supabase/Postgres schemas and baseline migration.
- `crucible` tables, closure trigger, idempotency key, pgvector column, RLS, and
  private grants.
- `lg_checkpoints` schema boundary.
- Neo4j Community constraints and indexes.
- Docker Compose services for Neo4j, Redis, MinIO, and bucket init.
- FastAPI health and dependency probes.
- Local and hosting env examples.
- Offline database foundation validator.

Not implemented yet:

- Product API endpoints beyond health.
- Typed repository layer for Postgres, Neo4j, Redis, and S3.
- MCP tool server.
- LangGraph research-loop package.
- Context Broker ingestion and embeddings.
- Execution backend adapters.
- Approval/resume workflow.
- Replay workflow.
- Product UI for DAG, evidence, traces, approvals, and replay.
- CI and live integration verification.

## Non-Functional Targets

- DAG queries under 100 ms for 10k-node trees.
- Domain graph queries under 200 ms for 1M-node graphs.
- Overnight program cost under 20 USD where possible.
- Crash recovery through LangGraph durable execution and Postgres checkpoints.
- Graceful degradation when Neo4j is unavailable.
- Self-hostable local development through Docker Compose plus Supabase local DB.

## Open Decisions

- Whether replay-critical programs require mandatory deterministic mode or an
  opt-in program setting.
- How aggressive automatic confirmation runs should be for quarantined
  hypotheses.
- Whether v2 extraction uses spaCy plus LLM extraction or a dedicated extraction
  model.
- How much DAG aggregation and virtualization the first UI release should ship.
- Whether the first launch should include only LocalBackend or include Modal in
  the public demo path.
