alter table public.candidates
  add column if not exists lawful_basis text,
  add column if not exists privacy_notice_version text,
  add column if not exists source_type text not null default 'recruiter_entry';

alter table public.candidates
  drop constraint if exists candidates_lawful_basis_check,
  add constraint candidates_lawful_basis_check
    check (lawful_basis is null or lawful_basis in (
      'consent', 'contract', 'legal_obligation',
      'legitimate_interests', 'public_task', 'vital_interests'
    )),
  drop constraint if exists candidates_source_type_check,
  add constraint candidates_source_type_check
    check (source_type in (
      'recruiter_entry', 'career_page', 'job_application',
      'referral', 'agency', 'import', 'cv_upload', 'other'
    ));

create unique index if not exists candidates_org_email_lower_uidx
  on public.candidates (organization_id, lower(trim(email)))
  where email is not null and trim(email) <> '';

comment on column public.candidates.lawful_basis is
  'Applicable processing basis recorded by the organisation; not a substitute for jurisdiction-specific legal review.';
comment on column public.candidates.privacy_notice_version is
  'Version identifier of the privacy notice presented at the point of collection.';
comment on column public.candidates.source_type is
  'Origin of the candidate record.';
