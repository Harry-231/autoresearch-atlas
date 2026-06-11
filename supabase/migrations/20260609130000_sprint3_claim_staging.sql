-- Sprint 3: claim staging area for gated tool writes.
-- The MCP/REST `record_claim` tool writes here, never to crucible.claims; promotion
-- to durable truth is the approval path (Sprint 7). Idempotent.

create table if not exists crucible.claim_staging (
  id uuid primary key default extensions.gen_random_uuid(),
  hypothesis_id uuid not null references crucible.hypotheses(id) on delete restrict,
  run_id uuid references crucible.runs(id) on delete set null,
  statement text not null,
  source_artifact_ref text,
  proposed_confidence numeric(5, 4) not null default 0.5000,
  status text not null default 'staged',
  created_at timestamptz not null default now(),
  constraint claim_staging_statement_not_blank check (length(btrim(statement)) > 0),
  constraint claim_staging_confidence_range check (
    proposed_confidence >= 0 and proposed_confidence <= 1
  ),
  constraint claim_staging_status_valid check (status in ('staged', 'promoted', 'rejected'))
);

create index if not exists claim_staging_hypothesis_idx
  on crucible.claim_staging (hypothesis_id);

alter table crucible.claim_staging enable row level security;
