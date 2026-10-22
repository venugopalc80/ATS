-- AQERITH recruitment workflow automation foundation.
-- Application code must still enforce tenant membership and action permissions at execution time.
create table if not exists public.workflow_definitions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  name text not null check (length(trim(name)) between 1 and 120),
  description text,
  draft_definition jsonb not null default '{}'::jsonb check (jsonb_typeof(draft_definition) = 'object'),
  status text not null default 'draft' check (status in ('draft','published','disabled')),
  created_by uuid references public.profiles(id) on delete set null,
  updated_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, id)
);
create index if not exists workflow_definitions_org_status_idx
  on public.workflow_definitions(organization_id, status, updated_at desc);

create table if not exists public.workflow_versions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  workflow_id uuid not null,
  version_number integer not null check (version_number > 0),
  trigger_event text not null check (trigger_event in (
    'application.created','application.stage_changed','interview.scheduled',
    'interview.feedback_overdue','offer.approved'
  )),
  definition jsonb not null check (jsonb_typeof(definition) = 'object'),
  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  published_at timestamptz,
  unique (workflow_id, version_number),
  unique (organization_id, id),
  foreign key (organization_id, workflow_id)
    references public.workflow_definitions(organization_id, id) on delete cascade
);
alter table public.workflow_definitions
  add column if not exists active_version_id uuid;
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'workflow_definitions_active_version_fk') then
    alter table public.workflow_definitions
      add constraint workflow_definitions_active_version_fk
      foreign key (organization_id, active_version_id)
      references public.workflow_versions(organization_id, id) on delete set null;
  end if;
end $$;

create table if not exists public.workflow_runs (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  workflow_id uuid not null,
  workflow_version_id uuid not null,
  event_name text not null,
  event_id text not null,
  idempotency_key text not null,
  status text not null default 'queued' check (status in (
    'queued','running','waiting_approval','succeeded','failed','cancelled','skipped'
  )),
  event_payload jsonb not null default '{}'::jsonb check (jsonb_typeof(event_payload) = 'object'),
  result_summary jsonb not null default '{}'::jsonb,
  error_code text,
  error_message text,
  attempts integer not null default 0 check (attempts >= 0),
  next_action_at timestamptz,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, idempotency_key),
  foreign key (organization_id, workflow_id)
    references public.workflow_definitions(organization_id, id) on delete cascade,
  foreign key (organization_id, workflow_version_id)
    references public.workflow_versions(organization_id, id) on delete restrict
);
create index if not exists workflow_runs_org_status_idx
  on public.workflow_runs(organization_id, status, created_at desc);
create index if not exists workflow_runs_due_idx
  on public.workflow_runs(status, next_action_at) where status in ('queued','waiting_approval','failed');

create table if not exists public.workflow_actions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  run_id uuid not null,
  step_key text not null,
  action_type text not null,
  status text not null default 'pending' check (status in (
    'pending','running','waiting_approval','succeeded','failed','skipped'
  )),
  idempotency_key text not null,
  input_payload jsonb not null default '{}'::jsonb,
  output_payload jsonb not null default '{}'::jsonb,
  error_code text,
  error_message text,
  attempts integer not null default 0 check (attempts >= 0),
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (run_id, step_key),
  unique (organization_id, idempotency_key),
  foreign key (organization_id, run_id)
    references public.workflow_runs(organization_id, id) on delete cascade
);
create index if not exists workflow_actions_run_idx
  on public.workflow_actions(organization_id, run_id, created_at);

create table if not exists public.workflow_approvals (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  run_id uuid not null,
  action_id uuid not null,
  status text not null default 'pending' check (status in ('pending','approved','rejected','cancelled')),
  requested_by uuid references public.profiles(id) on delete set null,
  decided_by uuid references public.profiles(id) on delete set null,
  decision_note text,
  requested_at timestamptz not null default now(),
  decided_at timestamptz,
  unique (organization_id, action_id),
  foreign key (organization_id, run_id)
    references public.workflow_runs(organization_id, id) on delete cascade,
  foreign key (organization_id, action_id)
    references public.workflow_actions(organization_id, id) on delete cascade
);
create index if not exists workflow_approvals_pending_idx
  on public.workflow_approvals(organization_id, status, requested_at desc);

alter table public.workflow_definitions enable row level security;
alter table public.workflow_versions enable row level security;
alter table public.workflow_runs enable row level security;
alter table public.workflow_actions enable row level security;
alter table public.workflow_approvals enable row level security;

drop policy if exists workflow_definitions_member_all on public.workflow_definitions;
create policy workflow_definitions_member_all on public.workflow_definitions
  for all using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));
drop policy if exists workflow_versions_member_all on public.workflow_versions;
create policy workflow_versions_member_all on public.workflow_versions
  for all using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));
drop policy if exists workflow_runs_member_all on public.workflow_runs;
create policy workflow_runs_member_all on public.workflow_runs
  for all using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));
drop policy if exists workflow_actions_member_all on public.workflow_actions;
create policy workflow_actions_member_all on public.workflow_actions
  for all using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));
drop policy if exists workflow_approvals_member_all on public.workflow_approvals;
create policy workflow_approvals_member_all on public.workflow_approvals
  for all using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));
