# Sprint 8 — Product UI MVP

**Layer:** Product surface · **Status:** `Not Started` · **Milestone:** Product MVP

## Goal

Build the first usable product surface for program progress and trust — the web UI
on top of the now-complete FastAPI control plane.

## Why now (bottom-up)

Everything the UI shows (DAG, runs, traces, approvals, evidence) is a real, stable API
after S2–S7. Building the UI last means it integrates against finished contracts, not
moving targets.

## Feature scope

- Program list/detail.
- DAG visualization — **server-aggregated, paged, virtualized** (REFINEMENT R5.1).
- Hypothesis detail + run detail (score vector, critic verdict, artifacts, trace link).
- Live trace panel with **budget burn-down / cost meter** (R4.3).
- Approvals queue (the trust surface) — TTL countdown, cost delta, audit (R4.2).
- Evidence graph (Neo4j: contradiction edges highlighted) (R5.3).
- Single-tenant auth for local use.

## Deliverables

- Next.js routes for programs, hypotheses, runs, approvals, evidence.
- Typed FastAPI client module.
- `packages/ui` shadcn/ui components + design tokens (R5.2).
- SSE trace integration; approval decision UI.

## Checklist

- [ ] Tailwind + shadcn/ui design system in `packages/ui`; tokens defined once.
- [ ] Typed API client; UI calls **FastAPI only** (no DB/runtime/secret access).
- [ ] Program list + detail (budget burn-down visible).
- [ ] DAG view: collapse rejected/quarantined subtrees, lazy-expand, virtualized.
- [ ] DAG renders large trees without raw client-side dumping (> cap → WebGL renderer).
- [ ] Hypothesis detail links to run, claims, artifacts, and trace; and back.
- [ ] Run detail shows score vector, critic verdict, artifacts.
- [ ] Live trace panel + cost meter update during a run over SSE (reconnect+backoff).
- [ ] Approvals queue: approve/deny (keyboard), TTL countdown, cost delta, audit trail.
- [ ] Evidence graph highlights contradiction edges.
- [ ] Degraded context shows a `degraded` badge (honest states, R4.5).
- [ ] WCAG 2.1 AA: contrast, keyboard nav, focus order, reduced-motion canvas.

## Acceptance criteria

- [ ] User can create/select a program and inspect its DAG.
- [ ] DAG view supports collapsed or paged large trees.
- [ ] Hypothesis detail links to run, claims, artifacts, and traces.
- [ ] Approval queue can approve or deny pending requests.
- [ ] Live trace panel updates during local runs.
- [ ] UI never uses server-only secrets or database connection strings.

## Definition of Done

Core screens delivered (program, DAG, hypothesis, run, approvals, evidence); user flows
pass (inspect DAG, watch run, decide approval, replay run); a11y audit passes; no secret
reaches the client bundle.

## Risks / notes

- DAG performance is the main risk; the server-aggregated endpoint from S2 is the
  enabler. Set a front-end performance budget and test against a seeded large tree.
