-- 027: tenant-scoped, database-generated public job references.
-- Existing non-empty job_code values are preserved. New references are allocated
-- atomically per organisation and remain immutable for the lifetime of the job.

alter table public.organizations
  add column if not exists job_reference_prefix text not null default 'JOB',
  add column if not exists job_reference_next_number bigint not null default 1;

alter table public.organizations
  add constraint organizations_job_reference_prefix_check
  check (job_reference_prefix ~ '^[A-Z][A-Z0-9]{1,7}$');

alter table public.organizations
  add constraint organizations_job_reference_next_number_check
  check (job_reference_next_number > 0);

create or replace function public.next_job_reference(p_organization_id uuid)
returns text
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
  v_prefix text;
  v_number bigint;
begin
  update public.organizations
     set job_reference_next_number = job_reference_next_number + 1,
         updated_at = now()
   where id = p_organization_id
   returning job_reference_prefix, job_reference_next_number - 1
        into v_prefix, v_number;

  if not found then
    raise exception 'Organisation not found for job reference allocation'
      using errcode = '23503';
  end if;

  return v_prefix || '-' || lpad(v_number::text, 3, '0');
end;
$$;

revoke all on function public.next_job_reference(uuid) from public, anon, authenticated;

create or replace function public.assign_job_reference()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
begin
  if tg_op = 'INSERT' then
    if new.job_code is null or btrim(new.job_code) = '' then
      new.job_code := public.next_job_reference(new.organization_id);
    end if;
  elsif new.job_code is distinct from old.job_code then
    raise exception 'Job reference numbers are immutable'
      using errcode = '23514';
  end if;
  return new;
end;
$$;

-- Backfill only missing references; do not alter any existing client/system code.
update public.jobs
   set job_code = public.next_job_reference(organization_id)
 where job_code is null or btrim(job_code) = '';

-- Ensure the next generated number is above any already-issued reference using
-- this organisation's configured prefix and the standard numeric suffix.
-- Install the trigger after backfilling so even a previously-null reference
-- cannot subsequently be assigned or changed through direct table updates.
drop trigger if exists jobs_assign_reference on public.jobs;
create trigger jobs_assign_reference
before insert or update of job_code on public.jobs
for each row execute function public.assign_job_reference();

update public.organizations o
   set job_reference_next_number = greatest(
     o.job_reference_next_number,
     coalesce((
       select max((substring(j.job_code from length(o.job_reference_prefix) + 2))::bigint) + 1
         from public.jobs j
        where j.organization_id = o.id
          and j.job_code ~ ('^' || o.job_reference_prefix || '-[0-9]+$')
     ), 1)
   );

do $$
begin
  if exists (
    select 1 from public.jobs
     where job_code is not null
     group by organization_id, job_code
    having count(*) > 1
  ) then
    raise exception 'Duplicate existing job_code values exist within an organisation; resolve them before applying migration 027';
  end if;
end;
$$;

create unique index if not exists jobs_organization_job_code_uidx
  on public.jobs (organization_id, job_code)
  where job_code is not null;

comment on column public.organizations.job_reference_prefix is
  'Configurable prefix for automatically generated public job references.';
comment on column public.organizations.job_reference_next_number is
  'Next per-organisation job reference number; incremented atomically by next_job_reference.';
