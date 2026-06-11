# Sprint 9 — Observability, Evals & CI

**Layer:** Quality gates · **Status:** `Not Started` · **Milestone:** Launch

## Goal

Make quality, cost, and regressions measurable and enforced before launch.

## Why now (bottom-up)

The full system exists (S0–S8). Now wire the **pluggable tracer**, prove the Critic
with a labeled eval, and gate the repo with CI + a cost guard so the project stays
correct and affordable as it grows.

## Feature scope

- GitHub Actions CI (install, typecheck, lint, schema validate, API check, tests).
- Schema-drift + unsafe-Neo4j-schema gate.
- Pluggable `Tracer` wired to the OSS default (Langfuse/OTel); LangSmith optional (R1.2).
- Critic reliability eval dataset (gamed/leaky/regressed, known-bad labels) + catch rate.
- Proposer quality eval dataset.
- Demo cost guard (fails on drift above the < $20 target).

## Deliverables

- `.github/workflows/ci.yml`
- tracer env docs + adapter wiring
- eval harness + datasets
- demo regression program + cost summary output

## Checklist

- [ ] CI runs on PRs and `main`: install, `pnpm check-types`, lint, ruff,
      `pnpm db:validate`, `pnpm api:check`, `pnpm api:test`.
- [ ] CI fails on schema drift or unsafe Neo4j schema additions.
- [ ] CI checks both pnpm and uv workspaces.
- [ ] `Tracer` adapter selected by config; default OSS tracer works with no proprietary dep.
- [ ] `runs.trace_id` persisted for every traced run; node↔trace round-trip verified.
- [ ] Critic reliability dataset + evaluator; catch-rate reported.
- [ ] Proposer quality dataset + evaluator.
- [ ] Cost guard reports per-run token/$ for the demo and fails on drift.

## Acceptance criteria

- [ ] CI runs on pull requests and `main`.
- [ ] CI fails on schema drift or unsafe Neo4j schema additions.
- [ ] CI checks pnpm and uv workspaces.
- [ ] Tracer trace ids are persisted on runs.
- [ ] Cost guard reports token and spend estimates for the demo.

## Definition of Done

Required CI jobs pass (install, typecheck, lint, schema validate, API check, tests);
three eval datasets created (critic reliability, proposer quality, cost regression);
the Critic catch rate is measured and recorded — the prerequisite for any future
agent-count expansion.

## Risks / notes

- Self-host requirement means the **default** tracer must be OSS and single-container.
  Do not make LangSmith a hard dependency anywhere in CI or runtime.
