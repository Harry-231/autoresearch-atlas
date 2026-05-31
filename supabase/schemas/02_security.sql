revoke all on schema crucible from public;
revoke all on schema crucible from anon;
revoke all on schema crucible from authenticated;

revoke all on schema lg_checkpoints from public;
revoke all on schema lg_checkpoints from anon;
revoke all on schema lg_checkpoints from authenticated;

revoke all on all tables in schema crucible from anon;
revoke all on all sequences in schema crucible from anon;
revoke all on all functions in schema crucible from anon;

revoke all on all tables in schema crucible from authenticated;
revoke all on all sequences in schema crucible from authenticated;
revoke all on all functions in schema crucible from authenticated;

alter default privileges in schema crucible
  revoke all on tables from anon, authenticated;

alter default privileges in schema crucible
  revoke all on sequences from anon, authenticated;

alter default privileges in schema crucible
  revoke all on functions from anon, authenticated;

alter table crucible.programs enable row level security;
alter table crucible.hypotheses enable row level security;
alter table crucible.hypothesis_closure enable row level security;
alter table crucible.runs enable row level security;
alter table crucible.claims enable row level security;
alter table crucible.approvals enable row level security;
alter table crucible.budgets enable row level security;
alter table crucible.events enable row level security;
