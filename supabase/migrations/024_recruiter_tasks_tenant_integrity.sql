-- Enforce organisation consistency for recruiter task relationships.
-- Preflight before changing constraints so existing cross-tenant rows are reported
-- explicitly and the migration never silently repairs or deletes business data.

do $$
begin
  if exists (
    select 1
    from public.recruiter_tasks t
    join public.candidates c on c.id = t.candidate_id
    where t.candidate_id is not null
      and t.organization_id <> c.organization_id
  ) then
    raise exception
      'Cannot apply recruiter task tenant constraints: recruiter_tasks contains candidate/organisation mismatches';
  end if;

  if exists (
    select 1
    from public.recruiter_tasks t
    join public.jobs j on j.id = t.job_id
    where t.job_id is not null
      and t.organization_id <> j.organization_id
  ) then
    raise exception
      'Cannot apply recruiter task tenant constraints: recruiter_tasks contains job/organisation mismatches';
  end if;
end;
$$;

-- PostgreSQL requires a unique key matching the referenced composite columns.
-- The UUID primary keys already make these pairs unique; these indexes expose
-- the tenant-qualified keys required by the composite foreign keys.
create unique index if not exists candidates_id_organization_id_uidx
  on public.candidates (id, organization_id);

create unique index if not exists jobs_id_organization_id_uidx
  on public.jobs (id, organization_id);

-- Replace the candidate-only FK with a tenant-qualified FK. Preserve the
-- existing cascade behaviour when a candidate is deleted.
alter table public.recruiter_tasks
  drop constraint if exists recruiter_tasks_candidate_id_fkey;

alter table public.recruiter_tasks
  drop constraint if exists recruiter_tasks_candidate_org_fkey;

alter table public.recruiter_tasks
  add constraint recruiter_tasks_candidate_org_fkey
  foreign key (candidate_id, organization_id)
  references public.candidates (id, organization_id)
  on delete cascade;

-- Keep the original job_id FK (ON DELETE SET NULL) so deleting a job does not
-- delete the task. This additional FK ensures the job belongs to the same org.
-- When the original FK sets job_id to NULL, MATCH SIMPLE makes this FK pass.
alter table public.recruiter_tasks
  drop constraint if exists recruiter_tasks_job_org_fkey;

alter table public.recruiter_tasks
  add constraint recruiter_tasks_job_org_fkey
  foreign key (job_id, organization_id)
  references public.jobs (id, organization_id)
  on delete no action;
