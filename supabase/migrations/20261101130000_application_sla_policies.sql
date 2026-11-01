-- Idea 04: organisation-configurable recruitment service-level targets.
-- Defaults are operational suggestions, not legal or regulatory requirements.
create table if not exists public.application_sla_policies (
  organization_id uuid primary key references public.organizations(id) on delete cascade,
  initial_review_minutes integer not null default 1440 check (initial_review_minutes between 1 and 43200),
  first_recruiter_action_minutes integer not null default 2880 check (first_recruiter_action_minutes between 1 and 43200),
  candidate_follow_up_minutes integer not null default 2880 check (candidate_follow_up_minutes between 1 and 43200),
  post_interview_update_minutes integer not null default 1440 check (post_interview_update_minutes between 1 and 43200),
  timezone text not null default 'UTC' check (length(trim(timezone)) between 1 and 100),
  business_days_only boolean not null default true,
  business_hours_start time not null default time '09:00',
  business_hours_end time not null default time '17:00',
  working_days smallint[] not null default array[1,2,3,4,5]::smallint[],
  enabled boolean not null default true,
  updated_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint application_sla_business_hours_valid check (business_hours_end > business_hours_start),
  constraint application_sla_working_days_valid check (
    cardinality(working_days) between 1 and 7
    and working_days <@ array[1,2,3,4,5,6,7]::smallint[]
  )
);

alter table public.application_sla_policies enable row level security;
revoke all on public.application_sla_policies from public, anon, authenticated;
drop policy if exists application_sla_policy_member_read on public.application_sla_policies;
create policy application_sla_policy_member_read on public.application_sla_policies
  for select using (public.is_org_member(organization_id));
