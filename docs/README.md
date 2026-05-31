# Autoresearch Atlas Docs

This folder contains the product, architecture, data model, and delivery
planning references for Crucible v2 / Autoresearch Atlas.

## Planning Documents

| Page | Purpose |
| --- | --- |
| [system_design.md](./system_design.md) | Implementation-facing system design synthesized from the SRS, ADR, and datastore docs |
| [sprints.md](./sprints.md) | Sprint plan with measurable acceptance criteria and feature-set milestones |
| [DESIGN.md](./DESIGN.md) | Original LangGraph/LangChain/LangSmith architecture narrative |
| [ADR-0001-database-architecture.md](./ADR-0001-database-architecture.md) | Accepted database architecture decision |
| [crucible_v2_srs (2).html](./crucible_v2_srs%20(2).html) | HTML Software Requirements Specification |

## Data Model References

| Page | Store | Contents |
| --- | --- | --- |
| [neo4j.md](./neo4j.md) | Neo4j 5 Community | Domain graph labels, properties, relationships, constraints, and indexes |
| [redis-and-object-store.md](./redis-and-object-store.md) | Redis + MinIO/S3 | Live trace stream keys and artifact object layout |

Executable definitions live outside this folder:

- Postgres and pgvector schema: `supabase/schemas/`
- Supabase migration history: `supabase/migrations/`
- Neo4j constraints and indexes: `schema/neo4j/`

If prose docs ever disagree with executable schema files, the executable schema
files win.

## Store Boundaries

```text
programs -> hypotheses -> runs -> events
                 |            |
                 |            +-> claims
                 |
                 +-> hypothesis_closure

Postgres crucible      = durable research truth
Postgres lg_checkpoints = disposable LangGraph runtime recovery state
Neo4j                  = domain graph memory
Redis                  = live trace transport before persistence
MinIO/S3               = immutable artifacts referenced by rows
```

Two boundaries carry the design:

- Session state is not research state. LangGraph checkpoints can be pruned
  without losing research results.
- Rows hold references, not blobs. Large artifacts live in object storage, and
  database columns ending in `_ref` store object keys or prefixes.
