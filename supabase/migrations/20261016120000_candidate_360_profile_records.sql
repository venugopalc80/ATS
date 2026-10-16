-- Candidate 360 structured profile records.
-- Backend API owns writes; browser roles receive no direct table access.
-- Apply to ATS-Staging only after review. Do not apply to production as part of this PR.

create unique index if not exists candidates_id_organization_id_uidx
  on public.candidates (id, organization_id);

create table if not exists public.candidate_employment_history (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  candidate_id uuid not null,
  employer_name text not null check (length(trim(employer_name)) between 1 and 200),
  job_title text not null check (length(trim(job_title)) between 1 and 200),
  location text,
  employment_type text,
  start_date date,
  end_date date,
  is_current boolean not null default false,
  description text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint candidate_employment_dates_valid check (end_date is null or start_date is null or end_date >= start_date),
  constraint candidate_employment_current_end_valid check (not is_current or end_date is null),
  constraint candidate_employment_candidate_org_fk foreign key (candidate_id, organization_id)
    references public.candidates (id, organization_id) on delete cascade
);

create table if not exists public.candidate_education (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  candidate_id uuid not null,
  institution_name text not null check (length(trim(institution_name)) between 1 and 200),
  qualification text,
  field_of_study text,
  start_date date,
  end_date date,
  grade text,
  description text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint candidate_education_dates_valid check (end_date is null or start_date is null or end_date >= start_date),
  constraint candidate_education_candidate_org_fk foreign key (candidate_id, organization_id)
    references public.candidates (id, organization_id) on delete cascade
);

create table if not exists public.candidate_certifications (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  candidate_id uuid not null,
  name text not null check (length(trim(name)) between 1 and 200),
  issuing_organisation text,
  credential_id text,
  credential_url text,
  issued_on date,
  expires_on date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint candidate_certification_dates_valid check (expires_on is null or issued_on is null or expires_on >= issued_on),
  constraint candidate_certification_candidate_org_fk foreign key (candidate_id, organization_id)
    references public.candidates (id, organization_id) on delete cascade
);

create table if not exists public.candidate_languages (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  candidate_id uuid not null,
  language text not null check (length(trim(language)) between 1 and 100),
  proficiency text check (proficiency is null or proficiency in ('basic','conversational','professional','fluent','native')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint candidate_language_unique_per_candidate unique (candidate_id, language),
  constraint candidate_language_candidate_org_fk foreign key (candidate_id, organization_id)
    references public.candidates (id, organization_id) on delete cascade
);

create index if not exists candidate_employment_org_candidate_idx
  on public.candidate_employment_history (organization_id, candidate_id, start_date desc);
create index if not exists candidate_education_org_candidate_idx
  on public.candidate_education (organization_id, candidate_id, end_date desc);
create index if not exists candidate_certifications_org_candidate_idx
  on public.candidate_certifications (organization_id, candidate_id, expires_on);
create index if not exists candidate_languages_org_candidate_idx
  on public.candidate_languages (organization_id, candidate_id, language);

alter table public.candidate_employment_history enable row level security;
alter table public.candidate_education enable row level security;
alter table public.candidate_certifications enable row level security;
alter table public.candidate_languages enable row level security;

drop policy if exists candidate_employment_member_read on public.candidate_employment_history;
create policy candidate_employment_member_read on public.candidate_employment_history
  for select to authenticated using (public.is_org_member(organization_id));
drop policy if exists candidate_education_member_read on public.candidate_education;
create policy candidate_education_member_read on public.candidate_education
  for select to authenticated using (public.is_org_member(organization_id));
drop policy if exists candidate_certifications_member_read on public.candidate_certifications;
create policy candidate_certifications_member_read on public.candidate_certifications
  for select to authenticated using (public.is_org_member(organization_id));
drop policy if exists candidate_languages_member_read on public.candidate_languages;
create policy candidate_languages_member_read on public.candidate_languages
  for select to authenticated using (public.is_org_member(organization_id));

revoke all on public.candidate_employment_history from anon, authenticated;
revoke all on public.candidate_education from anon, authenticated;
revoke all on public.candidate_certifications from anon, authenticated;
revoke all on public.candidate_languages from anon, authenticated;
grant select on public.candidate_employment_history to authenticated;
grant select on public.candidate_education to authenticated;
grant select on public.candidate_certifications to authenticated;
grant select on public.candidate_languages to authenticated;
