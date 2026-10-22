-- Permit a candidate to reapply after a prior application is rejected or withdrawn,
-- while preventing concurrent/accidental duplicate active applications.
alter table public.applications
  drop constraint if exists applications_job_id_candidate_id_key;

create unique index if not exists applications_active_job_candidate_uidx
  on public.applications (job_id, candidate_id)
  where status not in ('rejected', 'withdrawn');
