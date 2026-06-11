# Sprint 7 — Critic, Approvals, Budgets & Replay

**Layer:** Trust & governance · **Status:** `Not Started` · **Milestone:** Trust loop

## Goal

Add the trust and governance loop around autonomous execution: an independent Critic,
multi-metric evaluation, budget enforcement, human approvals, and replay.

## Why now (bottom-up)

The loop (S5) can now reason over real evidence (S6). This sprint makes its decisions
**trustworthy and reversible**: the Critic catches gaming/leakage/regression, approvals
gate risk, budgets cap spend, and replay reproduces kept runs.

## Feature scope

- Critic subgraph on a **separate model config** (different family by default).
- Multi-metric evaluator (primary, secondary, cost, reproducibility, novelty,
  domain confidence) → `keep|reject|quarantine|escalate`.
- Budget spend tracking from trace cost + adaptive beam response (R3.4).
- Approval records + decisions + LangGraph interrupt/resume.
- TTL sweeper (auto-deny, recorded).
- Replay endpoint from immutable refs; opt-in determinism (seed + pinned versions).

## Deliverables

- critic subgraph, evaluator service
- `GET /approvals?status=pending`, `POST /approvals/{id}/decide`
- `POST /runs/{id}/replay`
- budget update service, approval sweeper

## Checklist

- [ ] Critic returns schema-validated `CriticVerdict`; runs on independent model config.
- [ ] Evaluator maps verdict + scores to `keep|reject|quarantine|escalate`.
- [ ] Over-budget or risky work creates a `pending` approval row and `interrupt()`s.
- [ ] `POST /approvals/{id}/decide` resumes the parked thread; audit stamped.
- [ ] TTL expiry auto-denies with a recorded reason (sweeper).
- [ ] Approvals never auto-granted from agent/document text.
- [ ] Budget spend accrues from trace cost; soft-warning band before hard cap.
- [ ] Adaptive beam widens/narrows with budget headroom + recent kept-rate.
- [ ] `POST /runs/{id}/replay` re-executes from immutable artifact/event/context refs.
- [ ] Determinism mode is opt-in per program (seed + pinned model versions).

## Acceptance criteria

- [ ] Critic returns structured verdicts.
- [ ] Evaluator maps verdicts to keep, reject, quarantine, or escalate.
- [ ] Over-budget or risky work creates pending approval rows.
- [ ] Approval decisions resume parked graph runs.
- [ ] TTL expiry auto-denies and records audit state.
- [ ] Replay uses immutable artifact and event refs.

## Definition of Done

Governance decisions covered (approve, deny, expire); evaluator states covered (keep,
reject, quarantine, escalate); replay smoke test passes for one kept run; a run that
exceeds budget halts or escalates rather than overspending.

## Risks / notes

- Quarantined hypotheses get **at most one** auto-confirmation run, only if budget
  headroom exceeds a configured threshold; else hold for human triage (REFINEMENT §7).
- Critic value is only real once measured — the eval dataset in S9 gates any future
  agent-count expansion.
