-- Organisation-scoped recruiter tasks and candidate follow-ups for the AQERITH dashboard.
create unique index if not exists candidates_id_org_unique on public.candidates(id, organization_id);
create unique index if not exists jobs_id_org_unique on public.jobs(id, organization_id);
create table if not exists public.recruiter_tasks (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  title text not null check (char_length(btrim(title)) between 1 and 200),
  description text,
  task_type text not null default 'general' check (task_type in ('general','candidate_follow_up','vacancy_follow_up','interview_follow_up')),
  status text not null default 'open' check (status in ('open','in_progress','completed','cancelled')),
  priority text not null default 'normal' check (priority in ('low','normal','high','urgent')),
  due_at timestamptz,
  candidate_id uuid,
  job_id uuid,
  assigned_to uuid references public.profiles(id) on delete set null,
  created_by uuid references public.profiles(id) on delete set null,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint recruiter_tasks_candidate_org_fk foreign key (candidate_id, organization_id)
    references public.candidates(id, organization_id) on delete cascade,
  constraint recruiter_tasks_job_org_fk foreign key (job_id, organization_id)
    references public.jobs(id, organization_id) on delete cascade
);
create index if not exists recruiter_tasks_org_status_due_idx
  on public.recruiter_tasks(organization_id, status, due_at);
create index if not exists recruiter_tasks_assignee_status_due_idx
  on public.recruiter_tasks(organization_id, assigned_to, status, due_at);
alter table public.recruiter_tasks enable row level security;
create policy recruiter_tasks_member_select on public.recruiter_tasks
  for select to authenticated using (public.is_org_member(organization_id));
create policy recruiter_tasks_member_insert on public.recruiter_tasks
  for insert to authenticated with check (public.is_org_member(organization_id));
create policy recruiter_tasks_member_update on public.recruiter_tasks
  for update to authenticated using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));
create policy recruiter_tasks_member_delete on public.recruiter_tasks
  for delete to authenticated using (public.is_org_member(organization_id));
