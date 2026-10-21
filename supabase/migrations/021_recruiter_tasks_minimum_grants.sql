-- Strip default elevated privileges, then grant only row-level operations.
revoke all on table public.recruiter_tasks from anon, authenticated;
grant select, insert, update, delete on table public.recruiter_tasks to authenticated;
