drop policy if exists recruiter_tasks_member_insert on public.recruiter_tasks;
create policy recruiter_tasks_member_insert on public.recruiter_tasks
  for insert to authenticated
  with check (
    public.is_org_member(recruiter_tasks.organization_id)
    and recruiter_tasks.created_by = auth.uid()
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

drop policy if exists recruiter_tasks_member_update on public.recruiter_tasks;
create policy recruiter_tasks_member_update on public.recruiter_tasks
  for update to authenticated
  using (public.is_org_member(recruiter_tasks.organization_id))
  with check (
    public.is_org_member(recruiter_tasks.organization_id)
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
