-- 010_record_history_and_append_only_notes.sql
-- Preserve field-level change history for core ATS records.
-- Sensitive resume content and vector embeddings are deliberately excluded.

create or replace function public.capture_record_change()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  old_data jsonb;
  new_data jsonb;
  changed_fields jsonb := '{}'::jsonb;
  field_name text;
  org_id uuid;
  row_id uuid;
  actor_id uuid;
begin
  if tg_op = 'INSERT' then
    old_data := '{}'::jsonb;
    new_data := to_jsonb(new);
    org_id := (new_data ->> 'organization_id')::uuid;
    row_id := (new_data ->> 'id')::uuid;
  elsif tg_op = 'DELETE' then
    old_data := to_jsonb(old);
    new_data := '{}'::jsonb;
    org_id := (old_data ->> 'organization_id')::uuid;
    row_id := (old_data ->> 'id')::uuid;
  else
    old_data := to_jsonb(old);
    new_data := to_jsonb(new);
    org_id := (new_data ->> 'organization_id')::uuid;
    row_id := (new_data ->> 'id')::uuid;
  end if;

  old_data := old_data - 'resume_text' - 'embedding' - 'resume_path' - 'ai_summary';
  new_data := new_data - 'resume_text' - 'embedding' - 'resume_path' - 'ai_summary';

  if tg_op = 'UPDATE' then
    for field_name in
      select key from jsonb_each(new_data)
    loop
      if old_data -> field_name is distinct from new_data -> field_name then
        changed_fields := changed_fields || jsonb_build_object(
          field_name,
          jsonb_build_object('old', old_data -> field_name, 'new', new_data -> field_name)
        );
      end if;
    end loop;
    if changed_fields = '{}'::jsonb then
      return new;
    end if;
  else
    changed_fields := jsonb_build_object('snapshot', case when tg_op = 'INSERT' then new_data else old_data end);
  end if;

  begin
    actor_id := nullif(current_setting('app.actor_user_id', true), '')::uuid;
  exception when others then
    actor_id := null;
  end;

  if org_id is not null then
    insert into public.audit_events
      (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
    values
      (org_id, actor_id, lower(tg_op), tg_table_name, row_id,
       jsonb_build_object('changed_fields', changed_fields));
  end if;

  if tg_op = 'DELETE' then return old; end if;
  return new;
end;
$$;

drop trigger if exists candidates_record_history on public.candidates;
create trigger candidates_record_history
after insert or update or delete on public.candidates
for each row execute function public.capture_record_change();

drop trigger if exists jobs_record_history on public.jobs;
create trigger jobs_record_history
after insert or update or delete on public.jobs
for each row execute function public.capture_record_change();

drop trigger if exists clients_record_history on public.clients;
create trigger clients_record_history
after insert or update or delete on public.clients
for each row execute function public.capture_record_change();

drop trigger if exists applications_record_history on public.applications;
create trigger applications_record_history
after insert or update or delete on public.applications
for each row execute function public.capture_record_change();

-- Recruiter notes are append-only: revisions are new notes, not destructive edits.
drop policy if exists recruiter_notes_member_update on public.recruiter_notes;
drop policy if exists recruiter_notes_member_delete on public.recruiter_notes;

