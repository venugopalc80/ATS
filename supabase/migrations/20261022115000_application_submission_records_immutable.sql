-- Candidate answers and submission events are audit evidence; do not rewrite them in place.
-- Deletion remains possible for configured erasure/cascade workflows.
create or replace function public.prevent_application_submission_record_update()
returns trigger language plpgsql set search_path = public as $$
begin
  raise exception 'Submitted application answers and submission events are immutable';
end;
$$;

drop trigger if exists application_answers_no_update on public.application_answers;
create trigger application_answers_no_update
before update on public.application_answers
for each row execute function public.prevent_application_submission_record_update();

drop trigger if exists application_submission_events_no_update on public.application_submission_events;
create trigger application_submission_events_no_update
before update on public.application_submission_events
for each row execute function public.prevent_application_submission_record_update();
