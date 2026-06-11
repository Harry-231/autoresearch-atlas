-- Create the Supabase-style roles the declarative security schema references, so
-- supabase/schemas/02_security.sql (revoke ... from anon/authenticated) applies
-- cleanly on a plain Postgres container. Idempotent.

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    create role service_role nologin;
  end if;
end
$$;
