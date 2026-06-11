# Crucible v2 — Sprint Plan (Overview)

> Feature-based, **bottom-up** delivery: each sprint ships a stable layer the next
> one builds on, so the codebase stays clean and every layer is real before the
> thing above it depends on it. A sprint is `Done` only when its acceptance
> criteria pass in the repo (and, once CI exists, in CI).
>
> Companions: [`../SRS.md`](../SRS.md), [`../SYSTEM_DESIGN_v2.md`](../SYSTEM_DESIGN_v2.md),
> [`../REFINEMENT.md`](../REFINEMENT.md), [`../CODE_GUIDELINES.md`](../CODE_GUIDELINES.md).

## Status vocabulary

- `Not Started` — no committed implementation.
- `In Progress` — implementation exists but acceptance criteria do not all pass.
- `Blocked` — external dependency or unresolved decision prevents work.
- `Done` — acceptance criteria pass locally (and in CI once it exists).

## Cadence

One sprint ≈ 1–2 weeks for a small team. Early sprints are backend-heavy because the
UI depends on stable program / hypothesis / run / trace / approval APIs. Keep
acceptance criteria stable if a sprint splits; move unfinished scope forward.

## The bottom-up stack (why this order)

```
S10  Launch readiness (docs, profiles, security review)        ── packaging
S9   Observability, evals, CI, cost guard                      ── quality gates
S8   Product UI (DAG, detail, approvals, evidence, trace)      ── product surface
S7   Critic + approvals + budgets + replay                     ── trust & governance
S6   Context Broker + domain memory + hybrid retrieval         ── intelligence
S5   LangGraph research-loop MVP (proposer + evaluator)        ── reasoning
S4   Local/Container backend + event streaming                 ── execution
S3   MCP tool server (safe read boundary)                      ── agent data boundary
S2   Program import + DAG API                                  ── product data API
S1   FastAPI data-access layer (typed repositories)   [DONE]   ── server data plane
S0   Foundation: datastores, schema, health, validator [DONE]  ── ground
```

Each layer only depends on the ones below it. Nothing above S5 can be trusted until
the reasoning loop is real; nothing above S3 should reach data except through the
MCP boundary; nothing reaches the DB except through S1 repositories.

## Sprint index

| # | Sprint | Layer | Status | Doc |
| --- | --- | --- | --- | --- |
| 0 | Foundation & local runtime | Ground | `Done` | [Sprint-00](./Sprint-00-foundation.md) |
| 1 | FastAPI data-access layer | Server data plane | `Done` | [Sprint-01](./Sprint-01-data-access.md) |
| 2 | Program import & DAG API | Product data API | `Done` | [Sprint-02](./Sprint-02-program-dag-api.md) |
| 3 | MCP tool server | Agent data boundary | `In Progress` | [Sprint-03](./Sprint-03-mcp-tool-server.md) |
| 4 | Local/Container backend & streaming | Execution | `Not Started` | [Sprint-04](./Sprint-04-execution-backend.md) |
| 5 | LangGraph research-loop MVP | Reasoning | `Not Started` | [Sprint-05](./Sprint-05-research-loop.md) |
| 6 | Context Broker & domain memory | Intelligence | `Not Started` | [Sprint-06](./Sprint-06-context-broker.md) |
| 7 | Critic, approvals, budgets, replay | Trust & governance | `Not Started` | [Sprint-07](./Sprint-07-critic-approvals-replay.md) |
| 8 | Product UI MVP | Product surface | `Not Started` | [Sprint-08](./Sprint-08-product-ui.md) |
| 9 | Observability, evals, CI | Quality gates | `Not Started` | [Sprint-09](./Sprint-09-observability-evals-ci.md) |
| 10 | Launch readiness | Packaging | `Not Started` | [Sprint-10](./Sprint-10-launch-readiness.md) |

## Milestone map

| Milestone | Sprints | Outcome |
| --- | --- | --- |
| Foundation | 0–2 | Local system of record + program/DAG API usable. |
| Agent MVP | 3–5 | Agents read context, propose hypotheses, run local experiments. |
| Trust loop | 6–7 | Context, critic, approvals, budgets, replay functional. |
| Product MVP | 8 | Users inspect & operate programs from the web UI. |
| Launch | 9–10 | CI, evals, docs, release process ready. |

## Cross-cutting carries (pulled into the sprint where they land)

- `ProgramType` unification (`literature_synthesis` first) — schema in S2, exercised
  S5/S6 (REFINEMENT R0).
- `lite`/`full` Docker profiles (AGE / `LISTEN-NOTIFY` / FS) — introduced as an S0
  follow-up, hardened in S10 (R1.1).
- Pluggable `Tracer` (Langfuse/OTel default) — S9, but the seam is placed in S5 (R1.2).
- Local embeddings default + API opt-in — S6 (R2.3).
- Hybrid retrieval + context-pack cache — S6 (R3.1/R2.2).
- Novelty/dedup gate + adaptive beam — S5/S7 (R3.3/R3.4).
- Auth model for single-tenant local use — S8/S10.
- Determinism mode (opt-in) — S7.

## Recommended next sprint

**Sprint 3 — MCP Tool Server.** Sprints 0–2 are `Done`; the next bottom-up layer is the
safe, parameterized agent data boundary, which the reasoning loop (S5) builds on.

## How to work a sprint

1. Open the sprint doc; read Goal, Scope, and Definition of Done.
2. Implement against the **checklist**; keep PRs small and tied to checklist items.
3. Write tests that assert the **acceptance criteria** (see CODE_GUIDELINES §5).
4. Mark the sprint `Done` only when every acceptance criterion passes.
5. Update the index status above and any contract docs you changed.
