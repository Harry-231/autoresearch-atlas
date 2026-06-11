create type crucible.hypothesis_status as enum (
  'proposed',
  'running',
  'kept',
  'rejected',
  'quarantined',
  'escalated'
);

create type crucible.run_status as enum (
  'queued',
  'running',
  'succeeded',
  'failed',
  'cancelled'
);

create type crucible.approval_status as enum (
  'pending',
  'approved',
  'denied',
  'expired'
);

create type crucible.program_type as enum (
  'literature_synthesis',
  'ml_experiment'
);

create table crucible.programs (
  id uuid primary key default extensions.gen_random_uuid(),
  name text not null,
  type crucible.program_type not null default 'literature_synthesis',
  version text not null default 'v1',
  spec_yaml text not null,
  neo4j_graph_id text,
  owner text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint programs_name_not_blank check (length(btrim(name)) > 0),
  constraint programs_version_not_blank check (length(btrim(version)) > 0)
);

create table crucible.hypotheses (
  id uuid primary key default extensions.gen_random_uuid(),
  program_id uuid not null references crucible.programs(id) on delete restrict,
  parent_id uuid,
  depth integer not null,
  status crucible.hypothesis_status not null default 'proposed',
  proposal_hash text not null,
  patch_diff_ref text,
  compact_summary text not null default '',
  lg_thread_id text,
  proposer_run_id text,
  neo4j_context_ref text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint hypotheses_program_id_id_key unique (program_id, id),
  constraint hypotheses_parent_same_program
    foreign key (program_id, parent_id)
    references crucible.hypotheses(program_id, id)
    on delete restrict
    deferrable initially immediate,
  constraint hypotheses_depth_valid check (depth >= 0),
  constraint hypotheses_root_depth_valid check (
    (parent_id is null and depth = 0) or
    (parent_id is not null and depth > 0)
  ),
  constraint hypotheses_proposal_hash_not_blank check (length(btrim(proposal_hash)) > 0),
  constraint hypotheses_idempotency_key unique nulls not distinct (
    program_id,
    parent_id,
    proposal_hash
  )
);

create table crucible.hypothesis_closure (
  ancestor_id uuid not null references crucible.hypotheses(id) on delete restrict,
  descendant_id uuid not null references crucible.hypotheses(id) on delete restrict,
  depth integer not null,
  created_at timestamptz not null default now(),
  primary key (ancestor_id, descendant_id),
  constraint hypothesis_closure_depth_valid check (depth >= 0)
);

create table crucible.runs (
  id uuid primary key default extensions.gen_random_uuid(),
  hypothesis_id uuid not null references crucible.hypotheses(id) on delete restrict,
  backend text not null,
  status crucible.run_status not null default 'queued',
  started_at timestamptz,
  ended_at timestamptz,
  score_vector_json jsonb not null default '{}'::jsonb,
  critic_verdict_json jsonb not null default '{}'::jsonb,
  artifacts_ref text,
  event_log_ref text,
  langsmith_trace_id text,
  neo4j_context_snapshot_ref text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint runs_backend_not_blank check (length(btrim(backend)) > 0),
  constraint runs_ended_after_started check (
    ended_at is null or started_at is null or ended_at >= started_at
  )
);

create table crucible.claims (
  id uuid primary key default extensions.gen_random_uuid(),
  hypothesis_id uuid not null references crucible.hypotheses(id) on delete restrict,
  run_id uuid references crucible.runs(id) on delete set null,
  statement text not null,
  source_artifact_ref text,
  confidence numeric(5, 4) not null default 0.5000,
  neo4j_claim_id text,
  embedding extensions.vector(1536),
  created_at timestamptz not null default now(),
  constraint claims_statement_not_blank check (length(btrim(statement)) > 0),
  constraint claims_confidence_range check (confidence >= 0 and confidence <= 1)
);

create table crucible.claim_staging (
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

create table crucible.approvals (
  id uuid primary key default extensions.gen_random_uuid(),
  run_id uuid not null references crucible.runs(id) on delete restrict,
  kind text not null,
  status crucible.approval_status not null default 'pending',
  ttl interval not null default interval '24 hours',
  requested_at timestamptz not null default now(),
  decided_at timestamptz,
  decided_by text,
  audit jsonb not null default '{}'::jsonb,
  constraint approvals_kind_not_blank check (length(btrim(kind)) > 0),
  constraint approvals_ttl_positive check (ttl > interval '0 seconds'),
  constraint approvals_decision_fields_match check (
    (status = 'pending' and decided_at is null and decided_by is null) or
    (status <> 'pending' and decided_at is not null)
  )
);

create table crucible.budgets (
  id uuid primary key default extensions.gen_random_uuid(),
  program_id uuid not null references crucible.programs(id) on delete restrict,
  cap_usd numeric(12, 4) not null,
  spent_usd numeric(12, 4) not null default 0,
  updated_at timestamptz not null default now(),
  constraint budgets_program_unique unique (program_id),
  constraint budgets_cap_non_negative check (cap_usd >= 0),
  constraint budgets_spent_non_negative check (spent_usd >= 0)
);

create table crucible.events (
  id uuid primary key default extensions.gen_random_uuid(),
  run_id uuid not null references crucible.runs(id) on delete restrict,
  ts timestamptz not null default now(),
  kind text not null,
  payload jsonb not null default '{}'::jsonb,
  redis_stream_id text,
  created_at timestamptz not null default now(),
  constraint events_kind_not_blank check (length(btrim(kind)) > 0)
);

create unique index events_run_stream_id_key
  on crucible.events (run_id, redis_stream_id)
  where redis_stream_id is not null;

create unique index claims_neo4j_claim_id_key
  on crucible.claims (neo4j_claim_id)
  where neo4j_claim_id is not null;

create index hypotheses_program_parent_idx
  on crucible.hypotheses (program_id, parent_id);

create index hypotheses_program_parent_status_depth_idx
  on crucible.hypotheses (program_id, parent_id, status, depth);

create index hypotheses_program_status_created_idx
  on crucible.hypotheses (program_id, status, created_at desc);

create index hypothesis_closure_descendant_depth_idx
  on crucible.hypothesis_closure (descendant_id, depth);

create index hypothesis_closure_ancestor_depth_idx
  on crucible.hypothesis_closure (ancestor_id, depth);

create index runs_hypothesis_status_idx
  on crucible.runs (hypothesis_id, status);

create index claims_hypothesis_idx
  on crucible.claims (hypothesis_id);

create index claims_run_idx
  on crucible.claims (run_id);

create index claim_staging_hypothesis_idx
  on crucible.claim_staging (hypothesis_id);

create index events_run_ts_idx
  on crucible.events (run_id, ts);

create index claims_embedding_hnsw_idx
  on crucible.claims
  using hnsw (embedding extensions.vector_cosine_ops)
  where embedding is not null;

create function crucible.set_updated_at()
returns trigger
language plpgsql
set search_path = crucible, public, extensions
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger programs_set_updated_at
  before update on crucible.programs
  for each row
  execute function crucible.set_updated_at();

create trigger hypotheses_set_updated_at
  before update on crucible.hypotheses
  for each row
  execute function crucible.set_updated_at();

create trigger runs_set_updated_at
  before update on crucible.runs
  for each row
  execute function crucible.set_updated_at();

create function crucible.insert_hypothesis_closure()
returns trigger
language plpgsql
set search_path = crucible, public, extensions
as $$
begin
  insert into crucible.hypothesis_closure (ancestor_id, descendant_id, depth)
  values (new.id, new.id, 0);

  if new.parent_id is not null then
    insert into crucible.hypothesis_closure (ancestor_id, descendant_id, depth)
    select ancestor_id, new.id, depth + 1
    from crucible.hypothesis_closure
    where descendant_id = new.parent_id;
  end if;

  return new;
end;
$$;

create trigger hypotheses_insert_closure
  after insert on crucible.hypotheses
  for each row
  execute function crucible.insert_hypothesis_closure();

comment on table crucible.programs is
  'Research program declarations imported from research.yaml or program specs.';

comment on table crucible.hypotheses is
  'Append-only hypothesis DAG nodes. Nodes are never deleted.';

comment on table crucible.hypothesis_closure is
  'Transitive ancestor/descendant edges maintained on insert for fast DAG traversal.';

comment on table crucible.runs is
  'Execution attempts for hypotheses across local, Modal, Colab, or external backends.';

comment on table crucible.claims is
  'Empirical or extracted claims with optional pgvector embedding and Neo4j mirror id.';

comment on table crucible.events is
  'Durable replay log flushed from Redis live trace streams.';
