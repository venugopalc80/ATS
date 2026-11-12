alter table public.recruiter_tasks drop constraint if exists recruiter_tasks_candidate_id_fkey;
alter table public.recruiter_tasks
  add constraint recruiter_tasks_candidate_id_fkey
  foreign key (candidate_id) references public.candidates(id) on delete cascade;
