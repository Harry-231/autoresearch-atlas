# ADR-0001: Database architecture for Crucible v2

**Status:** Accepted
**Date:** 2026-05-31
**Deciders:** Crucible maintainers
**Related:** `docs/DESIGN.md` (§3 state separation, §8 data model, §11 NFRs); SRS v2.0

## Context

Crucible is a research operating system that runs autonomous, reproducible
research programs. The storage layer must support, simultaneously:

- A **durable, append-only hypothesis DAG** (programs, hypotheses, runs,
  claims, approvals, budgets, events) that the UI, replay, and provenance read
  from — nodes are never deleted.
- A **domain knowledge graph** (papers, methods, entities, claims,
  contradictions, hypothesis seeds) traversed to build agent context packs.
- **Semantic recall** over claims/notes/run summaries.
- **Large immutable artifacts** (diffs, checkpoints, logs, snapshots).
- **Live execution traces** streamed to the UI, then persisted for replay.
- **Agent runtime checkpoints** for crash recovery and resume-after-interrupt.

Forces at play:

- The SRS's spine rule — *the agent session is not the research state.* The
  reasoning runtime (LangGraph) keeps disposable per-thread checkpoints; those
  must never be conflated with, or able to corrupt, the permanent research
  truth.
- **Hard NFRs:** DAG queries < 100 ms @ 10k nodes; domain-graph queries
  < 200 ms @ 1M nodes; crash-recoverable; graceful degradation if the graph DB
  is down; secrets never reach agent prompts.
- **Constraints:** OSS, single-tenant, self-hostable with `docker compose up`
  on a laptop. Neo4j must be **Community Edition** (no clustering/HA/hot-backup,
  and no Enterprise-only NODE KEY / existence constraints).

## Decision

Adopt **polyglot persistence** with a strict ownership boundary:

1. **Postgres 16 + pgvector** is the system of record (schema `crucible`) **and**
   hosts pgvector semantic recall. It also stores LangGraph checkpoints, but in
   a **separate schema** (`lg_checkpoints`) owned by `langgraph-checkpoint-postgres`,
   so a runtime upgrade can never migrate or corrupt the system of record.
2. **Neo4j Community Edition** stores the domain graph. The app enforces
   required properties on write (existence constraints are Enterprise-only);
   only UNIQUE constraints + indexes are declared in schema.
3. **Redis** carries live trace/event streams, later persisted to `events`.
4. **MinIO / S3** stores artifacts; Postgres rows hold only object refs.

The DAG is an adjacency list (`parent_id`) plus a **closure table**
(`hypothesis_closure`) maintained by an `AFTER INSERT` trigger, giving O(depth)
subtree/ancestor queries without recursive-CTE scans. Idempotent writes key on
`(program_id, parent_id, proposal_hash)` (`UNIQUE NULLS NOT DISTINCT`).

**Implementation note (2026-06-01):** the current Supabase CLI rejects
`db.major_version = 16` in local `supabase/config.toml`. The local stack is
therefore configured with PostgreSQL 15, which still supports the schema's
required `UNIQUE NULLS NOT DISTINCT` feature. Hosted Supabase should use the
project's actual remote major version when linked.

## Options Considered

### Option A: Polyglot — Postgres+pgvector / Neo4j / Redis / MinIO (chosen)

| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium — four services, but each is single-purpose and Dockerized |
| Cost | Low — all OSS, runs on a laptop |
| Scalability | High for the workload — relational truth + native graph traversal + object store each scale on their own axis |
| Team familiarity | High — Postgres/Redis ubiquitous; Neo4j well-documented |

**Pros:** Each store plays to its strength; native graph traversal hits the
1M-node target; clean separation of disposable checkpoints from permanent truth;
matches the SRS/DESIGN data model directly.
**Cons:** More moving parts to run and back up; cross-store consistency is the
app's responsibility (mitigated by idempotent, write-truth-before-complete).

### Option B: Postgres-only (pgvector + recursive CTE/`ltree` + Apache AGE for graph)

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low ops (one engine) but high in-DB modelling complexity |
| Cost | Lowest |
| Scalability | Graph traversal at 1M nodes is the risk — AGE/`ltree` is less mature than a native graph engine for deep, relationship-heavy queries |
| Team familiarity | High |

**Pros:** One service to run, back up, and reason about; no cross-store
consistency.
**Cons:** Domain-graph traversal (contradiction chains, multi-hop derivations)
is exactly what a native graph engine is best at; emulating it risks the
< 200 ms NFR and adds query complexity. Rejected as primary, but see Consequences.

### Option C: Graph-first (Neo4j as primary store, everything as nodes/edges)

| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium |
| Cost | Low (CE) |
| Scalability | Loses cheap transactional/relational queries for runs/budgets/approvals |
| Team familiarity | Medium |

**Pros:** One model for everything; rich traversal.
**Cons:** Tabular/transactional concerns (budgets, approvals, event logs,
idempotent upserts) are awkward in a graph; CE single-instance has no HA, so
making it the *only* truth store raises durability risk. Rejected.

## Trade-off Analysis

The decisive factor is the SRS's two distinct query shapes: **transactional,
append-only, strongly-typed records** (DAG, runs, budgets, approvals) versus
**deep relationship traversal** (domain graph). Postgres is unbeatable for the
first; a native graph engine is unbeatable for the second. Option B collapses
both onto Postgres and risks the graph-traversal NFR; Option C collapses both
onto Neo4j and gives up transactional ergonomics and durability. Option A pays a
modest operational cost to let each query shape run on the right engine — and
the SRS already mandates graceful degradation, which removes the worst-case risk
of the extra graph dependency.

Co-locating LangGraph checkpoints in Postgres (separate schema) avoids a fifth
service while still honoring the session≠truth boundary.

## Consequences

**Easier**
- Hitting both latency NFRs (relational indexing + native graph traversal).
- Upgrading the agent runtime without risk to research truth (schema isolation).
- Local onboarding: one `docker compose up` brings up and initializes everything.

**Harder**
- Operating and backing up four services instead of one.
- Cross-store consistency is application logic (write-truth-before-complete +
  idempotent upserts + a `degraded` flag when Neo4j is unavailable).

**To revisit**
- If ops burden outweighs the benefit at single-tenant scale, fold the domain
  graph into Postgres (Option B with Apache AGE) behind the existing MCP query
  templates — agents wouldn't notice, since they see only the tool API.
- If HA becomes a real requirement, Neo4j CE is insufficient → Enterprise or a
  different graph store. Out of scope for v2.
- If checkpoint write volume becomes a hotspot, move the checkpointer to a
  dedicated Postgres/Redis instance.

## Action Items

1. [x] Author baseline schema: `schema/postgres/*.sql`, `schema/neo4j/*.cypher`.
2. [x] Provide local hosting via `docker-compose.yml` with auto-init for all stores.
3. [x] Provide a validator (`validate.py`) — offline structural + `--live`.
4. [ ] Wire the MCP tool server to hold DB creds and expose only parameterized queries.
5. [ ] Implement write-truth-before-complete + idempotent upserts in graph nodes.
6. [ ] Add a real migration tool (Alembic / versioned `.cypher`) past the v0 baseline.
7. [ ] Add `make validate` to CI and `make verify-live` to the integration suite.
