create index if not exists recruiter_tasks_assigned_to_idx on public.recruiter_tasks (assigned_to);
create index if not exists recruiter_tasks_created_by_idx on public.recruiter_tasks (created_by);
create index if not exists recruiter_tasks_completed_by_idx on public.recruiter_tasks (completed_by);
create index if not exists recruiter_tasks_candidate_id_idx on public.recruiter_tasks (candidate_id);
create index if not exists recruiter_tasks_job_id_idx on public.recruiter_tasks (job_id);

drop policy if exists recruiter_tasks_member_insert on public.recruiter_tasks;
create policy recruiter_tasks_member_insert on public.recruiter_tasks
  for insert to authenticated
  with check (
    public.is_org_member(recruiter_tasks.organization_id)
    and recruiter_tasks.created_by = (select auth.uid())
    and (recruiter_tasks.candidate_id is null or exists (
      select 1 from public.candidates c
      where c.id = recruiter_tasks.candidate_id
        and c.organization_id = recruiter_tasks.organization_id
    ))
    and (recruiter_tasks.job_id is null or exists (
      select 1 from public.jobs j
      where j.id = recruiter_tasks.job_id
        and j.organization_id = recruiter_tasks.organization_id
    ))
    and (recruiter_tasks.assigned_to is null or exists (
      select 1 from public.organization_members m
      where m.organization_id = recruiter_tasks.organization_id
        and m.user_id = recruiter_tasks.assigned_to
    ))
  );
