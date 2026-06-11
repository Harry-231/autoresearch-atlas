# Redis & object store conventions

Neither store has a declared schema, but both have **conventions** the code must
follow so traces replay and artifacts resolve. These are application contracts,
not DDL.

## Redis — live trace/event streams

Redis carries run events in real time; they are fanned to the UI over SSE and
then flushed into Postgres `events` for durable replay. After a successful
flush, a stream may be trimmed — Redis is **not** a system of record.

| Key | Type | Purpose |
| --- | --- | --- |
| `run:{run_id}:events` | Stream | append-only events for a run (`XADD`/`XREAD`) |
| `program:{program_id}:traces` | Pub/Sub channel | live trace fan-out to SSE subscribers |
| `run:{run_id}:status` | String | latest status for quick polling (optional) |

Conventions:
- Producers `XADD` event entries; the persister consumes via a consumer group
  and writes rows to `events`, recording the last-flushed stream id.
- Entry fields mirror the `events` row: `kind`, `payload` (JSON), `ts`.
- Treat everything in Redis as reconstructible from Postgres; never store the
  only copy of anything here.

## MinIO / S3 — artifacts

Large immutable blobs live here; Postgres rows store only the object key/prefix
(columns ending in `_ref`). Default bucket: `crucible-artifacts`.

| Postgres ref column | Object key convention | Contents |
| --- | --- | --- |
| `hypotheses.patch_diff_ref` | `programs/{program_id}/hypotheses/{hypothesis_id}/patch.diff` | the proposed patch |
| `runs.artifacts_ref` | `programs/{program_id}/runs/{run_id}/` (prefix) | checkpoints, logs, outputs |
| `runs.event_log_ref` | `programs/{program_id}/runs/{run_id}/events.jsonl` | persisted event log for replay |
| `claims.source_artifact_ref` | `programs/{program_id}/claims/{claim_id}/source.*` | provenance source |

Conventions:
- Objects are **write-once**; never mutate a key, write a new one and update the
  ref. This keeps replay deterministic.
- Key prefixes are program-scoped so a program's artifacts can be listed,
  archived, or deleted as a unit.
- Access via the S3 API (`S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`,
  `S3_SECRET_ACCESS_KEY` in `.env`); the bucket is created by the
  `minio-init` service when `pnpm infra:up` runs.
