# Sprint 6 — Context Broker & Domain Memory

**Layer:** Intelligence · **Status:** `Not Started` · **Milestone:** Trust loop

## Goal

Ingest sources and run outputs into the hybrid context engine so proposals are
conditioned on accumulated evidence — the system's memory.

## Why now (bottom-up)

The loop (S5) runs with thin context; this sprint fills the domain graph + vector
recall and upgrades `get_context_pack` (S3) from minimal to hybrid. It closes the
learning loop before the trust loop (S7) reasons over evidence/contradictions.

## Feature scope

- Paper/URL ingestion job.
- Entity + method extraction (spaCy spans + LLM claim/relation pass) — REFINEMENT.
- Claim extraction → Postgres `claims` + Neo4j/AGE nodes.
- Embedding generation: **local default** (`bge-small`/Ollama), API opt-in (R2.3).
- pgvector HNSW claim search.
- Hybrid retrieval (structural + lexical + semantic, reranked) — R3.1.
- Context-pack generation + cache (keyed `(hypothesis_id, graph_version)`) — R2.2.

## Deliverables

- Context Broker worker, ingestion queue/command.
- Neo4j/AGE write repository.
- Claim embedding service (pluggable embedder).
- Context-pack service feeding the MCP `get_context_pack` tool.

## Checklist

- [ ] Ingestion creates `Paper`, `Method`, `Entity`, `Claim` nodes + relationships.
- [ ] Extracted claims mirror into Postgres `claims` (`neo4j_claim_id` linkage).
- [ ] Embedder interface with local default + API adapter; batched, off the hot path.
- [ ] HNSW index on `claims.embedding`; `search_claims` returns ranked results.
- [ ] Hybrid retrieval combines graph + full-text + vector, then reranks.
- [ ] Context-pack cache with invalidation on new program claims.
- [ ] Broker re-runs after each kept run to feed new empirical claims back.
- [ ] Graph-store-down path returns lexical+semantic pack with `degraded=true`.

## Acceptance criteria

- [ ] Ingesting a sample paper creates Paper, Method, Entity, and Claim nodes.
- [ ] Extracted claims mirror into Postgres `claims`.
- [ ] Embeddings are stored for semantic recall.
- [ ] `get_context_pack` includes relevant claims, contradictions, prior run
      summaries, and degradation state.
- [ ] Graph-store-unavailable path still returns a pgvector-only context pack.

## Definition of Done

5 domain node types + 5 relationship types covered; context-pack latency measured on
seed data; hybrid retrieval beats vector-only on a small relevance check; degradation
verified.

## Risks / notes

- Keep extraction behind the Broker boundary so a dedicated extraction model can
  replace the LLM pass later without touching the graph schema.
