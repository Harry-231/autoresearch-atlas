# Neo4j domain graph

Neo4j 5 **Community Edition**. The relationship-native domain memory: papers,
methods, entities, claims, contradictions, and hypothesis seeds that the Context
Broker ingests and the MCP server traverses to build context packs. Source of
truth: [`schema/neo4j/`](../schema/neo4j/).

> **Community Edition limits.** Only `UNIQUE` constraints and indexes are
> declarable. `NODE KEY` and property-**existence** constraints are
> Enterprise-only, so the application must enforce required properties on write.
> There is also no clustering/HA — which is why the app falls back to a
> pgvector-only context pack (flagged `degraded=true`) when Neo4j is unavailable.

## Node labels

Every node carries a string `id` (uniqueness-constrained) and a `program_id`
scoping it to a research program. Other properties are written by the Context
Broker and are not constrained by the schema.

| Label | Key property | Typical properties | Meaning |
| --- | --- | --- | --- |
| `Paper` | `id` | `doi`, `title`, `year` | an ingested source paper |
| `Method` | `id` | `name` | a technique/approach |
| `Entity` | `id` | `name` | dataset/benchmark/model entity |
| `Claim` | `id` | `statement`, `program_id`, `confidence` | an extracted or empirical claim |
| `HypothesisSeed` | `id` | `program_id` | a candidate hypothesis derived from claims |

`Claim` nodes mirror rows in Postgres `claims` via `claims.neo4j_claim_id` ↔
`Claim.id`, so evidence can be followed in either store.

## Relationships

Created implicitly on write — no DDL required.

| Pattern | Meaning |
| --- | --- |
| `(:Paper)-[:USES]->(:Method)` | a paper applies a method |
| `(:Paper)-[:EVALUATES_ON]->(:Entity)` | a paper evaluates on a dataset/benchmark |
| `(:Claim)-[:SUPPORTS]->(:Claim)` | one claim supports another |
| `(:Claim)-[:CONTRADICTS]->(:Claim)` | one claim contradicts another (the evidence-graph signal the Critic uses) |
| `(:HypothesisSeed)-[:DERIVES_FROM]->(:Claim)` | a seed is grounded in a claim |

```
        ┌────────┐ USES         ┌────────┐
        │ Paper  │─────────────►│ Method │
        │        │ EVALUATES_ON ├────────┘
        │        │──────────┐
        └────────┘          ▼
                        ┌────────┐  SUPPORTS / CONTRADICTS
                        │ Entity │      ┌───────────────┐
                        └────────┘      ▼               │
                                    ┌────────┐──────────┘
                                    │ Claim  │◄───────────────┐
                                    └────────┘  DERIVES_FROM   │
                                                        ┌──────┴────────┐
                                                        │ HypothesisSeed│
                                                        └───────────────┘
```

## Constraints (uniqueness — each also creates a backing index)

| Name | Pattern |
| --- | --- |
| `paper_id` | `FOR (p:Paper) REQUIRE p.id IS UNIQUE` |
| `method_id` | `FOR (m:Method) REQUIRE m.id IS UNIQUE` |
| `entity_id` | `FOR (e:Entity) REQUIRE e.id IS UNIQUE` |
| `claim_id` | `FOR (c:Claim) REQUIRE c.id IS UNIQUE` |
| `hypothesis_seed_id` | `FOR (h:HypothesisSeed) REQUIRE h.id IS UNIQUE` |

## Indexes

| Name | Type | On | Serves |
| --- | --- | --- | --- |
| `paper_doi` | range | `(p:Paper) ON (p.doi)` | dedupe/lookup by DOI on ingest |
| `method_name` | range | `(m:Method) ON (m.name)` | entity resolution |
| `entity_name` | range | `(e:Entity) ON (e.name)` | entity resolution |
| `claim_program` | range | `(c:Claim) ON (c.program_id)` | per-program claim scans (MCP templates) |
| `claim_fulltext` | full-text | `(c:Claim) ON EACH [c.statement]` | keyword search over claims |

Targets domain-graph queries < 200 ms @ 1M nodes via these indexes plus
bounded-depth traversals in the MCP query templates (no raw Cypher from models).

## Access pattern

Agents never touch Neo4j directly. The MCP tool server exposes parameterized,
read-mostly tools — `get_context_pack`, `query_domain_graph`, `search_claims` —
holding the credentials so agents never receive secrets or arbitrary Cypher.
See `docs/DESIGN.md` §6.
