-- Section 7: AI governance, traceability and versioned authoring.
-- Additive only. All tenant-owned records are organisation scoped.
create table if not exists public.ai_use_cases (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  use_case_key text not null check (use_case_key in (
    'recruitment_assistant','job_description_writer','interview_preparation',
    'explainable_recommendations','fairness_monitoring','model_governance'
  )),
  name text not null,
  purpose text not null,
  owner_user_id uuid references public.profiles(id) on delete set null,
  provider_approved boolean not null default false,
  enabled boolean not null default false,
  approval_status text not null default 'pending' check (approval_status in ('pending','approved','suspended','retired')),
  limitations jsonb not null default '[]'::jsonb,
  retention_days integer not null default 90 check (retention_days between 1 and 3650),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, use_case_key)
);

create table if not exists public.ai_model_versions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  provider text not null,
  model_name text not null,
  model_version text not null,
  prompt_version text not null,
  intended_purpose text not null,
  data_processing_approved boolean not null default false,
  status text not null default 'draft' check (status in ('draft','evaluating','approved','disabled','retired')),
  configuration_fingerprint text,
  limitations jsonb not null default '[]'::jsonb,
  created_by uuid references public.profiles(id) on delete set null,
  approved_by uuid references public.profiles(id) on delete set null,
  approved_at timestamptz,
  created_at timestamptz not null default now(),
  unique (organization_id, provider, model_name, model_version, prompt_version)
);

create table if not exists public.ai_runs (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  use_case_id uuid references public.ai_use_cases(id) on delete set null,
  model_version_id uuid references public.ai_model_versions(id) on delete set null,
  actor_user_id uuid references public.profiles(id) on delete set null,
  task text not null,
  status text not null check (status in ('succeeded','failed','blocked','reported')),
  input_references jsonb not null default '[]'::jsonb,
  input_fingerprint text,
  output jsonb,
  evidence_references jsonb not null default '[]'::jsonb,
  limitations jsonb not null default '[]'::jsonb,
  feedback_status text check (feedback_status is null or feedback_status in ('helpful','incorrect','unsafe','other')),
  feedback_text text,
  reported_at timestamptz,
  retention_expires_at timestamptz not null,
  created_at timestamptz not null default now()
);

create table if not exists public.ai_recommendations (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  ai_run_id uuid references public.ai_runs(id) on delete set null,
  object_type text not null check (object_type in ('candidate','application','job','interview','job_description')),
  object_id uuid not null,
  purpose text not null,
  input_references jsonb not null default '[]'::jsonb,
  evidence jsonb not null default '[]'::jsonb,
  explanation text not null,
  limitations jsonb not null default '[]'::jsonb,
  model_version_id uuid references public.ai_model_versions(id) on delete set null,
  human_reviewed_by uuid references public.profiles(id) on delete set null,
  human_reviewed_at timestamptz,
  override_reason text,
  created_at timestamptz not null default now()
);

create table if not exists public.ai_job_description_versions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  job_id uuid not null references public.jobs(id) on delete cascade,
  version_number integer not null check (version_number > 0),
  content text not null,
  source_requirements jsonb not null default '[]'::jsonb,
  unsupported_facts jsonb not null default '[]'::jsonb,
  quality_findings jsonb not null default '[]'::jsonb,
  ai_run_id uuid references public.ai_runs(id) on delete set null,
  status text not null default 'draft' check (status in ('draft','in_review','approved','published','superseded')),
  created_by uuid references public.profiles(id) on delete set null,
  reviewed_by uuid references public.profiles(id) on delete set null,
  reviewed_at timestamptz,
  published_by uuid references public.profiles(id) on delete set null,
  published_at timestamptz,
  created_at timestamptz not null default now(),
  unique (job_id, version_number)
);

create table if not exists public.ai_interview_kits (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  job_id uuid not null references public.jobs(id) on delete cascade,
  job_version_reference text,
  version_number integer not null check (version_number > 0),
  competencies jsonb not null default '[]'::jsonb,
  questions jsonb not null default '[]'::jsonb,
  ai_run_id uuid references public.ai_runs(id) on delete set null,
  status text not null default 'draft' check (status in ('draft','in_review','approved','retired')),
  created_by uuid references public.profiles(id) on delete set null,
  reviewed_by uuid references public.profiles(id) on delete set null,
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  unique (job_id, version_number)
);

create table if not exists public.ai_evaluation_runs (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  model_version_id uuid not null references public.ai_model_versions(id) on delete cascade,
  suite_name text not null,
  dataset_version text not null,
  status text not null default 'running' check (status in ('running','passed','failed','cancelled')),
  pass_criteria jsonb not null,
  summary jsonb not null default '{}'::jsonb,
  started_by uuid references public.profiles(id) on delete set null,
  started_at timestamptz not null default now(),
  completed_at timestamptz
);

create table if not exists public.ai_evaluation_results (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  evaluation_run_id uuid not null references public.ai_evaluation_runs(id) on delete cascade,
  test_case_key text not null,
  passed boolean not null,
  metric_name text,
  metric_value numeric,
  expected_summary text,
  observed_summary text,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

-- Store only approved, aggregated fairness audit results; never infer protected traits.
create table if not exists public.ai_fairness_audits (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  audit_name text not null,
  dataset_version text not null,
  methodology text not null,
  outcome_metric text not null,
  aggregate_results jsonb not null,
  sample_sizes jsonb not null,
  missingness jsonb not null default '{}'::jsonb,
  uncertainty_notes jsonb not null default '[]'::jsonb,
  legal_review_reference text,
  reviewed_by uuid references public.profiles(id) on delete set null,
  reviewed_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists public.ai_incidents (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  ai_run_id uuid references public.ai_runs(id) on delete set null,
  model_version_id uuid references public.ai_model_versions(id) on delete set null,
  severity text not null check (severity in ('low','medium','high','critical')),
  category text not null,
  description text not null,
  status text not null default 'open' check (status in ('open','investigating','mitigated','closed')),
  remediation text,
  reported_by uuid references public.profiles(id) on delete set null,
  assigned_to uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  resolved_at timestamptz
);

create index if not exists ai_runs_org_created_idx on public.ai_runs(organization_id, created_at desc);
create index if not exists ai_runs_retention_idx on public.ai_runs(retention_expires_at);
create index if not exists ai_recommendations_object_idx on public.ai_recommendations(organization_id, object_type, object_id, created_at desc);
create index if not exists ai_job_description_versions_job_idx on public.ai_job_description_versions(organization_id, job_id, version_number desc);
create index if not exists ai_interview_kits_job_idx on public.ai_interview_kits(organization_id, job_id, version_number desc);
create index if not exists ai_evaluation_runs_org_idx on public.ai_evaluation_runs(organization_id, started_at desc);
create index if not exists ai_incidents_org_status_idx on public.ai_incidents(organization_id, status, created_at desc);

alter table public.ai_use_cases enable row level security;
alter table public.ai_model_versions enable row level security;
alter table public.ai_runs enable row level security;
alter table public.ai_recommendations enable row level security;
alter table public.ai_job_description_versions enable row level security;
alter table public.ai_interview_kits enable row level security;
alter table public.ai_evaluation_runs enable row level security;
alter table public.ai_evaluation_results enable row level security;
alter table public.ai_fairness_audits enable row level security;
alter table public.ai_incidents enable row level security;

drop policy if exists ai_use_cases_member_read on public.ai_use_cases;
create policy ai_use_cases_member_read on public.ai_use_cases for select to authenticated using (public.is_org_member(organization_id));
drop policy if exists ai_models_admin_read on public.ai_model_versions;
create policy ai_models_admin_read on public.ai_model_versions for select to authenticated using (public.is_org_admin(organization_id));
drop policy if exists ai_runs_member_read on public.ai_runs;
create policy ai_runs_member_read on public.ai_runs for select to authenticated using (public.is_org_member(organization_id));
drop policy if exists ai_recommendations_member_read on public.ai_recommendations;
create policy ai_recommendations_member_read on public.ai_recommendations for select to authenticated using (public.is_org_member(organization_id));
drop policy if exists ai_jd_versions_member_read on public.ai_job_description_versions;
create policy ai_jd_versions_member_read on public.ai_job_description_versions for select to authenticated using (public.is_org_member(organization_id));
drop policy if exists ai_interview_kits_member_read on public.ai_interview_kits;
create policy ai_interview_kits_member_read on public.ai_interview_kits for select to authenticated using (public.is_org_member(organization_id));
drop policy if exists ai_eval_runs_admin_read on public.ai_evaluation_runs;
create policy ai_eval_runs_admin_read on public.ai_evaluation_runs for select to authenticated using (public.is_org_admin(organization_id));
drop policy if exists ai_eval_results_admin_read on public.ai_evaluation_results;
create policy ai_eval_results_admin_read on public.ai_evaluation_results for select to authenticated using (public.is_org_admin(organization_id));
drop policy if exists ai_fairness_audits_admin_read on public.ai_fairness_audits;
create policy ai_fairness_audits_admin_read on public.ai_fairness_audits for select to authenticated using (public.is_org_admin(organization_id));
drop policy if exists ai_incidents_admin_read on public.ai_incidents;
create policy ai_incidents_admin_read on public.ai_incidents for select to authenticated using (public.is_org_admin(organization_id));

-- Browser clients may read through scoped RLS, but writes are API-only.
revoke insert, update, delete on public.ai_use_cases, public.ai_model_versions, public.ai_runs,
 public.ai_recommendations, public.ai_job_description_versions, public.ai_interview_kits,
 public.ai_evaluation_runs, public.ai_evaluation_results, public.ai_fairness_audits, public.ai_incidents
 from anon, authenticated;
grant select on public.ai_use_cases, public.ai_runs, public.ai_recommendations,
 public.ai_job_description_versions, public.ai_interview_kits to authenticated;
grant select on public.ai_model_versions, public.ai_evaluation_runs, public.ai_evaluation_results,
 public.ai_fairness_audits, public.ai_incidents to authenticated;
