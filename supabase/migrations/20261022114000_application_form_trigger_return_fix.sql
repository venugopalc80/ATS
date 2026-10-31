-- Published versions are immutable, while an unpublished draft may be deleted safely.
create or replace function public.prevent_published_form_version_mutation()
returns trigger language plpgsql set search_path = public as $$
begin
  if old.status = 'published' then
    raise exception 'Published application form versions are immutable; create a new draft version';
  end if;
  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end;
$$;

-- Use explicit trigger returns for PostgreSQL record values.
create or replace function public.prevent_published_form_question_mutation()
returns trigger language plpgsql set search_path = public as $$
declare target_version uuid;
declare current_status text;
begin
  if tg_op = 'DELETE' then
    target_version := old.form_version_id;
  else
    target_version := new.form_version_id;
  end if;
  select status into current_status from public.application_form_versions where id = target_version;
  if current_status = 'published' then
    raise exception 'Questions in published application form versions are immutable';
  end if;
  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end;
$$;
