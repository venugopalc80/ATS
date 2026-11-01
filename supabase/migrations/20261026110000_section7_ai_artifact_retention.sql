-- Section 7: apply explicit expiry dates to AI-generated drafts.
-- Reviewed/approved/published artifacts are deliberately excluded from automatic draft cleanup.
alter table public.ai_job_description_versions
  add column if not exists retention_expires_at timestamptz;

alter table public.ai_interview_kits
  add column if not exists retention_expires_at timestamptz;

create index if not exists ai_jd_versions_retention_idx
  on public.ai_job_description_versions (organization_id, retention_expires_at)
  where status in ('draft', 'in_review');

create index if not exists ai_interview_kits_retention_idx
  on public.ai_interview_kits (organization_id, retention_expires_at)
  where status in ('draft', 'in_review');
