-- Backfill expiry for drafts created before the retention columns were introduced.
-- Prefer the originating run's configured expiry; fall back to the use-case policy, then 90 days.
update public.ai_job_description_versions d
set retention_expires_at = coalesce(
  r.retention_expires_at,
  d.created_at + (coalesce(u.retention_days, 90) * interval '1 day')
)
from public.ai_runs r
left join public.ai_use_cases u on u.id = r.use_case_id
where d.ai_run_id = r.id
  and d.retention_expires_at is null;

update public.ai_job_description_versions d
set retention_expires_at = d.created_at + interval '90 days'
where d.retention_expires_at is null;

update public.ai_interview_kits k
set retention_expires_at = coalesce(
  r.retention_expires_at,
  k.created_at + (coalesce(u.retention_days, 90) * interval '1 day')
)
from public.ai_runs r
left join public.ai_use_cases u on u.id = r.use_case_id
where k.ai_run_id = r.id
  and k.retention_expires_at is null;

update public.ai_interview_kits k
set retention_expires_at = k.created_at + interval '90 days'
where k.retention_expires_at is null;
