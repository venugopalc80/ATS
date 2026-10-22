-- Idea 05: versioned application forms, questions, answers and submission audit events.
-- This migration is intentionally additive; existing candidate/application records remain the source of truth.

-- Composite keys make tenant ownership enforceable at the database boundary.
create unique index if not exists jobs_id_org_uidx on public.jobs (id, organization_id);
create unique index if not exists applications_id_org_uidx on public.applications (id, organization_id);

create table if not exists public.application_form_templates (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  name text not null check (length(trim(name)) between 1 and 160),
  description text,
  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, organization_id)
);

create table if not exists public.application_form_versions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  template_id uuid not null,
  version_number integer not null check (version_number > 0),
  status text not null default 'draft' check (status in ('draft','published','archived')),
  privacy_notice_text text not null check (length(trim(privacy_notice_text)) between 1 and 12000),
  privacy_notice_version text not null default '1',
  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  published_at timestamptz,
  unique (template_id, version_number),
  unique (id, organization_id),
  foreign key (template_id, organization_id)
    references public.application_form_templates(id, organization_id) on delete cascade
);

create table if not exists public.application_form_questions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  form_version_id uuid not null,
  question_key text not null check (question_key ~ '^[a-zA-Z][a-zA-Z0-9_]{0,79}$'),
  label text not null check (length(trim(label)) between 1 and 500),
  help_text text,
  field_type text not null check (field_type in ('text','textarea','email','phone','number','date','select','radio','checkbox','multi_select','boolean')),
  required boolean not null default false,
  options jsonb not null default '[]'::jsonb check (jsonb_typeof(options) = 'array'),
  validation jsonb not null default '{}'::jsonb check (jsonb_typeof(validation) = 'object'),
  is_eligibility boolean not null default false,
  position integer not null default 0,
  created_at timestamptz not null default now(),
  unique (form_version_id, question_key),
  unique (id, form_version_id, organization_id),
  foreign key (form_version_id, organization_id)
    references public.application_form_versions(id, organization_id) on delete cascade
);

create table if not exists public.job_application_forms (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  job_id uuid not null,
  form_version_id uuid not null,
  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, job_id),
  foreign key (job_id, organization_id) references public.jobs(id, organization_id) on delete cascade,
  foreign key (form_version_id, organization_id)
    references public.application_form_versions(id, organization_id) on delete restrict
);

create table if not exists public.application_answers (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  application_id uuid not null,
  form_version_id uuid not null,
  question_id uuid not null,
  answer jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (application_id, question_id),
  foreign key (application_id, organization_id) references public.applications(id, organization_id) on delete cascade,
  foreign key (form_version_id, organization_id)
    references public.application_form_versions(id, organization_id) on delete restrict,
  foreign key (question_id, form_version_id, organization_id)
    references public.application_form_questions(id, form_version_id, organization_id) on delete restrict
);

create table if not exists public.application_submission_events (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  application_id uuid not null references public.applications(id) on delete cascade,
  form_version_id uuid not null,
  event_type text not null check (event_type in ('submitted','confirmation_sent','candidate_withdrew','privacy_notice_acknowledged')),
  privacy_notice_version text,
  privacy_notice_acknowledged boolean not null default false,
  marketing_opt_in boolean not null default false,
  idempotency_key text,
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default now(),
  foreign key (application_id, organization_id) references public.applications(id, organization_id) on delete cascade,
  foreign key (form_version_id, organization_id)
    references public.application_form_versions(id, organization_id) on delete restrict
);

create unique index if not exists application_submission_events_idempotency_idx
  on public.application_submission_events (organization_id, idempotency_key)
  where idempotency_key is not null;
create index if not exists application_form_templates_org_idx
  on public.application_form_templates (organization_id, updated_at desc);
create index if not exists application_form_versions_template_idx
  on public.application_form_versions (template_id, version_number desc);
create index if not exists application_form_questions_version_position_idx
  on public.application_form_questions (form_version_id, position, id);
create index if not exists job_application_forms_job_idx
  on public.job_application_forms (organization_id, job_id);
create index if not exists application_answers_application_idx
  on public.application_answers (organization_id, application_id);
create index if not exists application_submission_events_application_idx
  on public.application_submission_events (organization_id, application_id, created_at desc);

alter table public.application_form_templates enable row level security;
alter table public.application_form_versions enable row level security;
alter table public.application_form_questions enable row level security;
alter table public.job_application_forms enable row level security;
alter table public.application_answers enable row level security;
alter table public.application_submission_events enable row level security;

drop policy if exists application_form_templates_member_all on public.application_form_templates;
create policy application_form_templates_member_all on public.application_form_templates
  for all using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));
drop policy if exists application_form_versions_member_all on public.application_form_versions;
create policy application_form_versions_member_all on public.application_form_versions
  for all using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));
drop policy if exists application_form_questions_member_all on public.application_form_questions;
create policy application_form_questions_member_all on public.application_form_questions
  for all using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));
drop policy if exists job_application_forms_member_all on public.job_application_forms;
create policy job_application_forms_member_all on public.job_application_forms
  for all using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));
drop policy if exists application_answers_member_all on public.application_answers;
create policy application_answers_member_all on public.application_answers
  for all using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));
drop policy if exists application_submission_events_member_all on public.application_submission_events;
create policy application_submission_events_member_all on public.application_submission_events
  for all using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));

comment on table public.application_form_templates is 'Reusable tenant-scoped application form templates.';
comment on table public.application_form_versions is 'Versioned immutable form snapshots; published versions are retained for audit.';
comment on table public.application_form_questions is 'Question definitions scoped to a specific immutable form version.';
comment on table public.application_answers is 'Candidate answers linked to the exact question and form version presented.';
comment on table public.application_submission_events is 'Append-oriented application submission and notice audit events.';
