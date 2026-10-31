-- Published versions are audit records. Changes must be made by creating a new draft version.
create or replace function public.prevent_published_form_version_mutation()
returns trigger language plpgsql set search_path = public as $$
begin
  if old.status = 'published' then
    raise exception 'Published application form versions are immutable; create a new draft version';
  end if;
  return new;
end;
$$;

drop trigger if exists application_form_versions_immutable on public.application_form_versions;
create trigger application_form_versions_immutable
before update or delete on public.application_form_versions
for each row execute function public.prevent_published_form_version_mutation();

create or replace function public.prevent_published_form_question_mutation()
returns trigger language plpgsql set search_path = public as $$
declare target_version uuid;
declare current_status text;
begin
  target_version := case when tg_op = 'DELETE' then old.form_version_id else new.form_version_id end;
  select status into current_status from public.application_form_versions where id = target_version;
  if current_status = 'published' then
    raise exception 'Questions in published application form versions are immutable';
  end if;
  return case when tg_op = 'DELETE' then old else new end;
end;
$$;

drop trigger if exists application_form_questions_immutable on public.application_form_questions;
create trigger application_form_questions_immutable
before insert or update or delete on public.application_form_questions
for each row execute function public.prevent_published_form_question_mutation();
