create schema if not exists extensions;

create extension if not exists pgcrypto with schema extensions;
create extension if not exists vector with schema extensions;

create schema if not exists crucible;
create schema if not exists lg_checkpoints;

comment on schema crucible is
  'Autoresearch Atlas durable system of record: programs, hypotheses, runs, claims, approvals, budgets, and events.';

comment on schema lg_checkpoints is
  'LangGraph runtime checkpoint schema. Disposable runtime state only; not product truth.';
