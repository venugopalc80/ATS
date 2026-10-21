-- Organisation-scoped recruiter tasks and candidate follow-ups for dashboard priorities.
create table if not exists public.recruiter_tasks (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  title text not null check (char_length(trim(title)) between 1 and 200),
  description text,
  task_type text not null default 'task' check (task_type in ('task','candidate_follow_up','vacancy_follow_up')),
  candidate_id uuid,
  job_id uuid,
  assigned_to uuid references auth.users(id) on delete set null,
  due_at timestamptz not null,
  status text not null default 'open' check (status in ('open','completed','cancelled')),
  created_by uuid not null references auth.users(id) on delete restrict,
  completed_by uuid references auth.users(id) on delete set null,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint recruiter_tasks_candidate_org_fk foreign key (candidate_id, organization_id)
    references public.candidates(id, organization_id) on delete cascade,
  constraint recruiter_tasks_job_org_fk foreign key (job_id, organization_id)
    references public.jobs(id, organization_id) on delete cascade,
  constraint recruiter_tasks_link_required check (task_type = 'task' or candidate_id is not null or job_id is not null)
);
create index if not exists recruiter_tasks_org_status_due_idx
  on public.recruiter_tasks (organization_id, status, due_at);
create index if not exists recruiter_tasks_assignee_idx
  on public.recruiter_tasks (organization_id, assigned_to, status, due_at);
alter table public.recruiter_tasks enable row level security;
drop policy if exists recruiter_tasks_member_select on public.recruiter_tasks;
create policy recruiter_tasks_member_select on public.recruiter_tasks
  for select to authenticated using (public.is_org_member(organization_id));
drop policy if exists recruiter_tasks_member_insert on public.recruiter_tasks;
create policy recruiter_tasks_member_insert on public.recruiter_tasks
  for insert to authenticated with check (public.is_org_member(organization_id) and created_by = auth.uid());
drop policy if exists recruiter_tasks_member_update on public.recruiter_tasks;
create policy recruiter_tasks_member_update on public.recruiter_tasks
  for update to authenticated using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));
