-- Sprint 2: program type + DAG read performance.
-- Adds the ProgramType discriminator (REFINEMENT R0) and a covering index for the
-- DAG list/subtree queries. Additive and backfill-safe: existing programs default
-- to 'literature_synthesis'.

-- Idempotent so it can be applied via the Supabase CLI or directly (asyncpg /
-- psql) and re-run safely.

do $$
begin
  if not exists (
    select 1
    from pg_type t
    join pg_namespace n on n.oid = t.typnamespace
    where t.typname = 'program_type'
      and n.nspname = 'crucible'
  ) then
    create type crucible.program_type as enum (
      'literature_synthesis',
      'ml_experiment'
    );
  end if;
end
$$;

alter table crucible.programs
  add column if not exists type crucible.program_type not null
    default 'literature_synthesis';

create index if not exists hypotheses_program_parent_status_depth_idx
  on crucible.hypotheses (program_id, parent_id, status, depth);
