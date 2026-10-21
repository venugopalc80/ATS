-- RLS does not protect TRUNCATE; do not grant anonymous table privileges.
revoke all on table public.recruiter_tasks from anon;
grant select, insert, update, delete on table public.recruiter_tasks to authenticated;
