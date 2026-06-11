# Sprint 4 — Local/Container Backend & Event Streaming

**Layer:** Execution · **Status:** `Not Started` · **Milestone:** Agent MVP

## Goal

Dispatch local experiment jobs and persist live trace events for replay, behind one
`Backend` protocol the reasoning loop (S5) calls.

## Why now (bottom-up)

S5's `run_experiment` node dispatches to a backend and parks on an interrupt. The
backend + run lifecycle + event path must be real before the loop can drive it.

## Feature scope

- `Backend` protocol.
- `LocalBackend` (subprocess/host) + `ContainerBackend` (Docker/SSH) — REFINEMENT R1.3.
- Run lifecycle state transitions.
- Stream producer (Redis Streams *full* / `LISTEN/NOTIFY` *lite*) behind one interface.
- Event persister from stream → Postgres `events`.
- Artifact writer to object store (MinIO/S3 *full* / FS *lite*).

## Deliverables

- `apps/api/src/autoresearch_api/backends/{base,local,container}.py`
- `POST /runs`, `GET /runs/{id}`, `GET /programs/{id}/stream`
- event-persister worker, artifact-store service

## Checklist

- [ ] `Backend` protocol: `submit`, `status`, `fetch_artifacts`, `stream_events`.
- [ ] `LocalBackend` runs a job and emits events; `ContainerBackend` runs in Docker/SSH.
- [ ] Optional `Modal`/`Colab` backends declared as entry-point plugins (stubs OK).
- [ ] Run lifecycle: `queued → running → succeeded|failed|cancelled` persisted to `runs`.
- [ ] Stream producer behind one interface; both Redis and `LISTEN/NOTIFY` wirings work.
- [ ] `GET /programs/{id}/stream` (SSE) delivers live events.
- [ ] Event persister writes stream entries into `crucible.events` (records last id).
- [ ] Artifact writer follows the documented object-key layout; writes are write-once.
- [ ] Stream loss after flush loses no replayable events (test).

## Acceptance criteria

- [ ] Submitting a local job creates a `runs` row.
- [ ] Run events are written to the live stream for the run.
- [ ] SSE stream receives live events for a program.
- [ ] Persister writes stream events into `crucible.events`.
- [ ] Artifact refs follow the documented object-key layout.
- [ ] Loss of the live stream after flush does not lose replayable events.

## Definition of Done

Run lifecycle states covered; event path covered end-to-end (produce → stream →
persist → replay-read); artifact write/read smoke cases pass for patch, run prefix,
and event log; both `LocalBackend` and `ContainerBackend` run the demo job.

## Risks / notes

- For `literature_synthesis`, the "job" is retrieve+read+synthesize — no GPU. Keep
  `JobSpec` general enough to carry both job kinds.
