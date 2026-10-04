create table if not exists public.interviews (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  application_id uuid not null references public.applications(id) on delete cascade,
  scheduled_at timestamptz not null,
  duration_minutes integer not null default 60 check (duration_minutes between 15 and 480),
  interview_type text not null default 'video',
  location text,
  interviewer_ids uuid[] not null default '{}',
  status text not null default 'scheduled' check (status in ('scheduled','completed','cancelled','rescheduled','no_show')),
  notes text,
  feedback text,
  outcome text,
  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists interviews_org_scheduled_idx on public.interviews(organization_id, scheduled_at);
create index if not exists interviews_application_idx on public.interviews(application_id);
alter table public.interviews enable row level security;
create policy interviews_member_all on public.interviews for all using (public.is_org_member(organization_id)) with check (public.is_org_member(organization_id));