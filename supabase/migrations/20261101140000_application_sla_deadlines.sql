-- Idea 04: persisted SLA deadlines for application workflow milestones.
create table if not exists public.application_sla_deadlines (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  application_id uuid not null references public.applications(id) on delete cascade,
  milestone text not null check (milestone in (
    'initial_review', 'first_recruiter_action', 'candidate_follow_up', 'post_interview_update'
  )),
  starts_at timestamptz not null,
  due_at timestamptz not null,
  status text not null default 'pending'
    check (status in ('pending', 'overdue', 'completed', 'paused')),
  completed_at timestamptz,
  last_calculated_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (application_id, milestone)
);

create index if not exists application_sla_deadlines_org_status_due_idx
  on public.application_sla_deadlines(organization_id, status, due_at);
create index if not exists application_sla_deadlines_app_idx
  on public.application_sla_deadlines(application_id, milestone);

alter table public.application_sla_deadlines enable row level security;
revoke all on public.application_sla_deadlines from public, anon, authenticated;
drop policy if exists application_sla_deadlines_member_read on public.application_sla_deadlines;
create policy application_sla_deadlines_member_read on public.application_sla_deadlines
  for select using (public.is_org_member(organization_id));
