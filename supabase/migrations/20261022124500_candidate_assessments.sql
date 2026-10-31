-- AQERITH Idea 11: candidate assessments and skills testing.
-- Additive migration. Review and apply to ATS-Staging only after code review; never apply to production as part of this change.

-- Composite unique indexes allow tenant-safe foreign keys to existing records.
create unique index if not exists jobs_organization_id_id_uidx on public.jobs(organization_id, id);
create unique index if not exists applications_organization_id_id_uidx on public.applications(organization_id, id);

create table if not exists public.assessment_templates (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  job_id uuid,
  name text not null check (length(trim(name)) between 1 and 160),
  description text,
  assessment_type text not null check (assessment_type in ('work_sample','technical_exercise','written_task','external_test')),
  instructions text not null check (length(trim(instructions)) between 1 and 8000),
  evaluation_guidance text,
  role_requirements text[] not null default '{}',
  accessibility_options jsonb not null default '{}'::jsonb check (jsonb_typeof(accessibility_options) = 'object'),
  provider_key text,
  status text not null default 'draft' check (status in ('draft','published','archived')),
  created_by uuid references public.profiles(id) on delete set null,
  updated_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, id),
  foreign key (organization_id, job_id) references public.jobs(organization_id, id) on delete set null (job_id)
);

create table if not exists public.assessment_assignments (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  application_id uuid not null,
  template_id uuid not null,
  status text not null default 'assigned' check (status in ('assigned','in_progress','submitted','under_review','completed','cancelled','expired','provider_error')),
  assigned_by uuid references public.profiles(id) on delete set null,
  due_at timestamptz,
  extended_due_at timestamptz,
  extension_reason text,
  accommodation_requested boolean not null default false,
  accommodation_arrangements text,
  instructions_snapshot text not null,
  provider_key text,
  provider_assignment_ref text,
  idempotency_key text,
  assigned_at timestamptz not null default now(),
  started_at timestamptz,
  submitted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, id),
  unique (organization_id, idempotency_key),
  foreign key (organization_id, application_id) references public.applications(organization_id, id) on delete cascade,
  foreign key (organization_id, template_id) references public.assessment_templates(organization_id, id) on delete restrict,
  check (extended_due_at is null or due_at is not null),
  check (extension_reason is null or length(trim(extension_reason)) <= 2000),
  check (accommodation_arrangements is null or length(accommodation_arrangements) <= 2000)
);

create table if not exists public.assessment_submissions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  assignment_id uuid not null,
  submission_type text not null check (submission_type in ('work_sample','technical_exercise','written_task','external_test')),
  text_content text,
  storage_path text,
  provider_submission_ref text,
  checksum_sha256 text check (checksum_sha256 is null or checksum_sha256 ~ '^[a-f0-9]{64}$'),
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  submitted_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  unique (organization_id, id),
  unique (organization_id, assignment_id, id),
  foreign key (organization_id, assignment_id) references public.assessment_assignments(organization_id, id) on delete cascade,
  check (text_content is null or length(text_content) <= 100000),
  check (storage_path is null or length(storage_path) <= 1000)
);

create table if not exists public.assessment_results (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  assignment_id uuid not null,
  submission_id uuid,
  source text not null check (source in ('human','provider','system')),
  methodology text not null check (length(trim(methodology)) between 1 and 2000),
  score numeric(7,2),
  max_score numeric(7,2),
  summary text,
  evidence jsonb not null default '[]'::jsonb check (jsonb_typeof(evidence) = 'array'),
  result_payload jsonb not null default '{}'::jsonb check (jsonb_typeof(result_payload) = 'object'),
  provider_key text,
  provider_result_ref text,
  received_at timestamptz not null default now(),
  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  unique (organization_id, id),
  unique (organization_id, assignment_id, id),
  foreign key (organization_id, assignment_id) references public.assessment_assignments(organization_id, id) on delete cascade,
  foreign key (organization_id, assignment_id, submission_id) references public.assessment_submissions(organization_id, assignment_id, id) on delete set null (submission_id),
  check ((score is null and max_score is null) or (score >= 0 and max_score > 0 and score <= max_score)),
  check (summary is null or length(summary) <= 8000)
);

create table if not exists public.assessment_reviews (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  assignment_id uuid not null,
  result_id uuid,
  reviewer_id uuid not null references public.profiles(id) on delete restrict,
  feedback text not null check (length(trim(feedback)) between 1 and 8000),
  recommendation text not null default 'review' check (recommendation in ('advance','review','not_recommended','no_recommendation')),
  reviewed_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  foreign key (organization_id, assignment_id) references public.assessment_assignments(organization_id, id) on delete cascade,
  foreign key (organization_id, assignment_id, result_id) references public.assessment_results(organization_id, assignment_id, id) on delete set null (result_id)
);

-- Upgrade-safe tenant and assignment integrity for environments where the assessment
-- tables were created by the earlier candidate_assessments migration. CREATE TABLE IF
-- NOT EXISTS does not retrofit constraints on pre-existing tables.
create unique index if not exists assessment_submissions_org_assignment_id_uidx
  on public.assessment_submissions (organization_id, assignment_id, id);
create unique index if not exists assessment_results_org_assignment_id_uidx
  on public.assessment_results (organization_id, assignment_id, id);

alter table public.assessment_results
  drop constraint if exists assessment_results_organization_id_submission_id_fkey,
  drop constraint if exists assessment_results_organization_id_assignment_id_submission_id_fkey;
alter table public.assessment_results
  add constraint assessment_results_assignment_submission_fk
  foreign key (organization_id, assignment_id, submission_id)
  references public.assessment_submissions (organization_id, assignment_id, id)
  on delete set null (submission_id);

alter table public.assessment_reviews
  drop constraint if exists assessment_reviews_organization_id_result_id_fkey,
  drop constraint if exists assessment_reviews_organization_id_assignment_id_result_id_fkey;
alter table public.assessment_reviews
  add constraint assessment_reviews_assignment_result_fk
  foreign key (organization_id, assignment_id, result_id)
  references public.assessment_results (organization_id, assignment_id, id)
  on delete set null (result_id);

-- Append-only operational history for assignment, deadline, accommodation and provider events.
create table if not exists public.assessment_assignment_events (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  assignment_id uuid not null,
  actor_user_id uuid references public.profiles(id) on delete set null,
  event_type text not null check (length(trim(event_type)) between 1 and 80),
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default now(),
  foreign key (organization_id, assignment_id) references public.assessment_assignments(organization_id, id) on delete cascade
);

-- Provider event IDs are unique per provider to prevent webhook replay.
create table if not exists public.assessment_provider_events (
  id uuid primary key default gen_random_uuid(),
  provider_key text not null check (length(trim(provider_key)) between 1 and 100),
  provider_event_id text not null check (length(trim(provider_event_id)) between 1 and 255),
  payload_sha256 text not null check (payload_sha256 ~ '^[a-f0-9]{64}$'),
  signature_verified boolean not null default false,
  processing_status text not null default 'received' check (processing_status in ('received','processed','ignored','failed')),
  failure_code text,
  processed_at timestamptz,
  created_at timestamptz not null default now(),
  unique (provider_key, provider_event_id)
);

create index if not exists assessment_templates_org_job_idx on public.assessment_templates(organization_id, job_id, status);
create index if not exists assessment_assignments_org_status_due_idx on public.assessment_assignments(organization_id, status, due_at);
create index if not exists assessment_assignments_application_idx on public.assessment_assignments(organization_id, application_id, created_at desc);
create index if not exists assessment_submissions_assignment_idx on public.assessment_submissions(organization_id, assignment_id, submitted_at desc);
create index if not exists assessment_results_assignment_idx on public.assessment_results(organization_id, assignment_id, received_at desc);
create index if not exists assessment_reviews_assignment_idx on public.assessment_reviews(organization_id, assignment_id, reviewed_at desc);
create index if not exists assessment_assignment_events_assignment_idx on public.assessment_assignment_events(organization_id, assignment_id, created_at desc);

alter table public.assessment_templates enable row level security;
alter table public.assessment_assignments enable row level security;
alter table public.assessment_submissions enable row level security;
alter table public.assessment_results enable row level security;
alter table public.assessment_reviews enable row level security;
alter table public.assessment_assignment_events enable row level security;
alter table public.assessment_provider_events enable row level security;

-- Browser clients receive no direct access. The authenticated FastAPI service validates
-- organisation membership and uses the server-side database connection.
revoke all on public.assessment_templates, public.assessment_assignments, public.assessment_submissions,
  public.assessment_results, public.assessment_reviews, public.assessment_assignment_events,
  public.assessment_provider_events from anon, authenticated;

create or replace function public.prevent_assessment_event_mutation()
returns trigger
language plpgsql
set search_path = ''
as 'BEGIN RAISE EXCEPTION ''assessment assignment events are append-only''; END;';

drop trigger if exists assessment_assignment_events_append_only on public.assessment_assignment_events;
create trigger assessment_assignment_events_append_only
before update or delete on public.assessment_assignment_events
for each row execute function public.prevent_assessment_event_mutation();

comment on table public.assessment_provider_events is 'Webhook idempotency ledger; stores payload hash and processing metadata, not full raw payloads.';
comment on column public.assessment_assignments.accommodation_arrangements is 'Record only practical arrangements needed to administer the assessment; do not record diagnoses.';
