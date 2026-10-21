alter table public.recruiter_tasks alter column created_by set default auth.uid();
revoke all on table public.recruiter_tasks from anon, authenticated;
grant select, delete on table public.recruiter_tasks to authenticated;
grant insert (organization_id,title,description,task_type,priority,due_at,candidate_id,job_id,assigned_to)
  on public.recruiter_tasks to authenticated;
grant update (title,description,status,priority,due_at,candidate_id,job_id,assigned_to,completed_at,updated_at)
  on public.recruiter_tasks to authenticated;
