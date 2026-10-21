create table if not exists public.recruiter_tasks (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  title text not null check (length(trim(title)) between 1 and 240),
  description text,
  task_type text not null default 'task' check (task_type in ('task','candidate_follow_up')),
  status text not null default 'open' check (status in ('open','completed','cancelled')),
  priority text not null default 'normal' check (priority in ('low','normal','high','urgent')),
  due_at timestamptz,
  candidate_id uuid references public.candidates(id) on delete set null,
  job_id uuid references public.jobs(id) on delete set null,
  assigned_to uuid references public.profiles(id) on delete set null,
  created_by uuid not null references public.profiles(id) on delete restrict,
  completed_at timestamptz,
  completed_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (task_type <> 'candidate_follow_up' or candidate_id is not null),
  check ((status = 'completed' and completed_at is not null) or (status <> 'completed' and completed_at is null))
);

create index if not exists recruiter_tasks_org_status_due_idx
  on public.recruiter_tasks (organization_id, status, due_at);
create index if not exists recruiter_tasks_org_assignee_due_idx
  on public.recruiter_tasks (organization_id, assigned_to, status, due_at);
create index if not exists recruiter_tasks_candidate_idx
  on public.recruiter_tasks (organization_id, candidate_id, due_at);

alter table public.recruiter_tasks enable row level security;
create policy recruiter_tasks_member_select on public.recruiter_tasks
  for select to authenticated
  using (public.is_org_member(organization_id));
create policy recruiter_tasks_member_insert on public.recruiter_tasks
  for insert to authenticated
  with check (
    public.is_org_member(organization_id)
    and created_by = auth.uid()
    and (candidate_id is null or exists (select 1 from public.candidates c where c.id = candidate_id and c.organization_id = recruiter_tasks.organization_id))
    and (job_id is null or exists (select 1 from public.jobs j where j.id = job_id and j.organization_id = recruiter_tasks.organization_id))
    and (assigned_to is null or exists (select 1 from public.organization_members m where m.organization_id = recruiter_tasks.organization_id and m.user_id = assigned_to))
  );
create policy recruiter_tasks_member_update on public.recruiter_tasks
  for update to authenticated
  using (public.is_org_member(organization_id))
  with check (
    public.is_org_member(organization_id)
    and (candidate_id is null or exists (select 1 from public.candidates c where c.id = candidate_id and c.organization_id = organization_id))
    and (job_id is null or exists (select 1 from public.jobs j where j.id = job_id and j.organization_id = organization_id))
    and (assigned_to is null or exists (select 1 from public.organization_members m where m.organization_id = organization_id and m.user_id = assigned_to))
  );
create policy recruiter_tasks_member_delete on public.recruiter_tasks
  for delete to authenticated
  using (public.is_org_member(organization_id));
