-- Idea 04: recruiter assignment and immutable assignment history.
-- A recruiter must be an active member of the same organisation.
create table if not exists public.application_assignments (
  application_id uuid primary key references public.applications(id) on delete cascade,
  organization_id uuid not null references public.organizations(id) on delete cascade,
  recruiter_id uuid,
  assigned_by uuid references public.profiles(id) on delete set null,
  assigned_at timestamptz,
  updated_at timestamptz not null default now(),
  constraint application_assignments_member_fk
    foreign key (organization_id, recruiter_id)
    references public.organization_members(organization_id, user_id)
    on delete set null (recruiter_id)
);

create index if not exists application_assignments_org_recruiter_idx
  on public.application_assignments(organization_id, recruiter_id);

create table if not exists public.application_assignment_history (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  application_id uuid not null references public.applications(id) on delete cascade,
  previous_recruiter_id uuid references public.profiles(id) on delete set null,
  new_recruiter_id uuid references public.profiles(id) on delete set null,
  actor_user_id uuid references public.profiles(id) on delete set null,
  reason text not null check (length(trim(reason)) between 1 and 1000),
  created_at timestamptz not null default now()
);

create index if not exists application_assignment_history_org_app_created_idx
  on public.application_assignment_history(organization_id, application_id, created_at desc);

alter table public.application_assignments enable row level security;
alter table public.application_assignment_history enable row level security;
revoke all on public.application_assignments from public, anon, authenticated;
revoke all on public.application_assignment_history from public, anon, authenticated;

drop policy if exists application_assignments_member_read on public.application_assignments;
create policy application_assignments_member_read on public.application_assignments
  for select using (public.is_org_member(organization_id));

drop policy if exists application_assignment_history_member_read on public.application_assignment_history;
create policy application_assignment_history_member_read on public.application_assignment_history
  for select using (public.is_org_member(organization_id));
