# Sprint 10 — Launch Readiness

**Layer:** Packaging · **Status:** `Not Started` · **Milestone:** Launch

## Goal

Package the project for external contributors and self-hosted use, so a stranger can
clone, run, and contribute confidently.

## Why now (bottom-up)

Everything works and is measured (S0–S9). The last layer is the human one: docs,
profiles, quickstart, security review, and a release process.

## Feature scope

- Contributor guide + local quickstart.
- `lite`/`full` profile hardening (AGE / `LISTEN-NOTIFY` / FS one-service path) (R1.1).
- Hosted deployment guide; migration + backup guide.
- Demo program docs (`lit-synthesis` primary, `nanochat` ml).
- Security review.
- Release checklist.

## Deliverables

- `CONTRIBUTING.md`, `docs/local_development.md`, `docs/hosting.md`, `docs/operations.md`
- `examples/lit-synthesis/README.md`, `examples/nanochat/README.md`
- release checklist

## Checklist

- [ ] `lite` profile boots the whole system with **one** service; verified from clean clone.
- [ ] `full` profile documented for scale (Neo4j/Redis/MinIO).
- [ ] New-contributor path: clone → `docker compose --profile lite up` → quickstart works.
- [ ] Hosted guide covers Supabase, graph, streams, and object-store env values.
- [ ] Backup/restore guidance for Postgres, Neo4j, and object storage.
- [ ] Security checklist: secrets, RLS, MCP boundaries, approval gates, sandbox isolation.
- [ ] `crucible quickstart` runs the demo end-to-end from a clean clone.
- [ ] License, README, and contributor docs consistent and current.

## Acceptance criteria

- [ ] New contributor can run the local stack from a clean clone.
- [ ] Hosted setup explains Supabase, graph, streams, and object-store env values.
- [ ] Backup/restore guidance covers Postgres, Neo4j, and object storage.
- [ ] Security checklist covers secrets, RLS, MCP boundaries, and approval gates.
- [ ] Demo program can be run end-to-end by following docs.

## Definition of Done

Docs walkthroughs verified from a clean clone (local-lite, local-full, hosted, demo);
release blockers open: 0; security review signed off.

## Cross-sprint backlog (pull in when needed)

- Modal / Colab backends (optional plugins) — hardened beyond stubs.
- UI virtualization strategy for very large DAGs (beyond the S8 baseline).
- Formal versioned migration tooling for Neo4j changes.
- Dedicated extraction-model evaluation (replace the LLM extraction pass).
- Active-learning policies, domain packs, multi-tenant — deferred past v2.
