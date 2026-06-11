# Sprint 5 — LangGraph Research-Loop MVP

**Layer:** Reasoning · **Status:** `Not Started` · **Milestone:** Agent MVP

## Goal

Add the first executable reasoning loop using **ids in graph state** and **durable
writes** for research truth — the engine that makes the system autonomous.

## Why now (bottom-up)

It depends on all three layers below it: the DAG API (S2) to record hypotheses, the
MCP boundary (S3) to read context, and the backend (S4) to run experiments. Building
it last among the agent layers keeps each dependency real, not mocked.

## Feature scope

- `langgraph.json` graph registration.
- `ProgramState` (ids + counters only).
- Research-loop graph: `select_frontier → expand → novelty_gate → run_experiment →
  evaluate → persist`.
- Proposer subgraph with structured `PatchProposal` output.
- Evaluator node (single-metric MVP; full multi-metric in S7).
- Postgres checkpointer on `lg_checkpoints`.
- Local/Container backend integration.
- **Tracer seam** placed now (vendor wired in S9) — REFINEMENT R1.2/R1.4.

## Deliverables

- `apps/api/src/autoresearch_api/agent/{graph,proposer,state,nodes}.py` (or `crucible/graph`)
- `langgraph.json`
- graph invocation script / `crucible run <program>` CLI command
- integration test using the `lit-synthesis` example

## Checklist

- [ ] `ProgramState` holds ids/counters only — no research content.
- [ ] Model routing via `init_chat_model("provider:model")` (config-driven).
- [ ] Proposer returns schema-validated `PatchProposal`; invalid → `revise` path.
- [ ] `novelty_gate` skips/merges near-duplicate proposals before a beam slot (R3.3).
- [ ] Beam-bounded fan-out via `Send`; results fan-in via `operator.add`.
- [ ] `run_experiment` dispatches to the backend and `interrupt()`s until resume.
- [ ] Durable hypothesis/run writes occur **before** node completion; idempotent upsert.
- [ ] Checkpointer configured on `lg_checkpoints`; restart resumes without duplicates.
- [ ] Success-memory few-shot from `status='kept'` hypotheses feeds the Proposer (R3.2).
- [ ] Tracer seam present (no-op/local adapter acceptable this sprint).

## Acceptance criteria

- [ ] Graph state stores ids and counters, not full research artifacts.
- [ ] Durable hypothesis/run writes occur before graph-node completion.
- [ ] Restart after checkpoint resumes without duplicating hypotheses.
- [ ] Proposer output is schema-validated.
- [ ] One local demo program creates ≥ 1 child hypothesis and ≥ 1 run.

## Definition of Done

Graph nodes delivered (select_frontier, expand, novelty_gate, run_experiment,
evaluate, persist); resume/idempotency tests pass (interrupted run, duplicate proposal
replay); the `lit-synthesis` example runs end-to-end locally and writes durable truth.

## Risks / notes

- Critic is **not** in this sprint — evaluator is single-metric MVP; the
  independent-model Critic and approvals arrive in S7. Keep `evaluate` pluggable.
