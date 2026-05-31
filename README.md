# Autoresearch Atlas

Autoresearch Atlas is the monorepo foundation for Crucible v2: a research
operating system with a durable hypothesis DAG, graph-native domain memory,
live trace streams, and immutable experiment artifacts.

The current repo keeps the Turborepo/Next.js starter apps in place while adding
the database and API foundation described by the Crucible v2 SRS and ADR.

## Architecture

The accepted database strategy is polyglot persistence with strict ownership
boundaries:

- Supabase-managed Postgres 16 + pgvector is the durable system of record in
  schema `crucible`.
- LangGraph checkpoints live in separate schema `lg_checkpoints`; this is
  disposable runtime recovery state, not research truth.
- Neo4j 5 Community Edition stores the domain graph for papers, methods,
  entities, claims, contradictions, and hypothesis seeds.
- Redis carries live run events before they are flushed to `crucible.events`.
- MinIO/S3 stores immutable blobs such as patch diffs, checkpoints, logs, and
  replay event logs.
- FastAPI in `apps/api` is the first server-side connection surface. Do not
  connect the Next.js frontend directly to the databases.

## Repository Layout

```text
apps/
  api/          uv-managed FastAPI control-plane foundation
  docs/         Next.js docs app from the starter
  web/          Next.js web app from the starter
packages/       shared TypeScript configs, eslint config, and UI stubs
schema/neo4j/   Neo4j Community-compatible constraints and indexes
supabase/       Supabase config, declarative SQL schemas, and migrations
tools/          offline validation scripts
```

## Local Setup

Requirements:

- Node.js 20 or newer
- pnpm 9
- uv
- Docker Desktop or another Docker-compatible runtime

Copy environment defaults:

```sh
cp .env.example .env
```

Start Supabase local Postgres:

```sh
pnpm db:supabase:start
```

Apply migrations if they are not already applied by your local reset/start
flow:

```sh
npx supabase migration up
```

Start Neo4j, Redis, and MinIO:

```sh
pnpm infra:up
```

Run the API:

```sh
pnpm api:dev
```

Check the service:

```sh
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/dependencies
```

## Hosted Setup

Use `.env.hosting.example` as the production template. The app server needs a
direct Supabase Postgres `DATABASE_URL`; this must never be exposed through
`NEXT_PUBLIC_*` variables or shipped to browser code.

Recommended hosted mapping:

- Supabase hosted Postgres for `crucible` and `lg_checkpoints`
- Managed Neo4j or self-hosted Neo4j Community where HA is not required
- Managed Redis for live streams
- S3-compatible storage for immutable artifacts

Deploy database changes with the Supabase CLI after linking a project:

```sh
npx supabase link
npx supabase db push
```

## Database Validation

Run offline structural checks:

```sh
pnpm db:validate
```

Run the API compile check:

```sh
pnpm api:check
```

The validation script checks for:

- required Postgres schemas, extensions, tables, trigger, RLS, and private
  grants
- Community-compatible Neo4j constraints and indexes
- complete local and hosting env templates
- FastAPI health probe coverage for Postgres, Neo4j, Redis, and S3

## Notes For Windows

If PowerShell blocks `pnpm.ps1`, call `pnpm.cmd` directly or run from a shell
where the pnpm command shim is allowed. This repo does not require changing the
frontend apps to use database clients directly; database access belongs in
`apps/api`.
