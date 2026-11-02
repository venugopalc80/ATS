-- Enforce that a recruiter task assignee belongs to the same organisation.
-- Fail explicitly rather than silently changing existing assignments.

do $$
begin
  if exists (
    select 1
    from public.recruiter_tasks t
    left join public.organization_members m
      on m.organization_id = t.organization_id
     and m.user_id = t.assigned_to
    where t.assigned_to is not null
      and m.user_id is null
  ) then
    raise exception
      'Cannot apply recruiter task assignee constraint: assigned_to contains an organisation membership mismatch';
  end if;
end;
$$;

alter table public.recruiter_tasks
  drop constraint if exists recruiter_tasks_assignee_org_fkey;

-- Column-list SET NULL is supported by PostgreSQL 15+ and deliberately clears
-- only assigned_to, preserving the task's non-null organisation_id.
alter table public.recruiter_tasks
  add constraint recruiter_tasks_assignee_org_fkey
  foreign key (organization_id, assigned_to)
  references public.organization_members (organization_id, user_id)
  on delete set null (assigned_to);
