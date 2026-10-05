-- Workflow audit attribution and lifecycle hardening.
create or replace function public.audit_workflow_status_change()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  actor_text text;
  actor_id uuid;
  entity_type_value text;
begin
  actor_text := current_setting('app.actor_user_id', true);
  if actor_text is null or actor_text = '' then
    actor_id := null;
  else
    actor_id := actor_text::uuid;
  end if;

  entity_type_value := case tg_table_name
    when 'applications' then 'application'
    when 'interviews' then 'interview'
    when 'offers' then 'offer'
    when 'placements' then 'placement'
    else tg_table_name
  end;

  if new.status is distinct from old.status then
    insert into public.audit_events
      (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
    values
      (new.organization_id, actor_id, tg_table_name || '.status_changed', entity_type_value, new.id,
       jsonb_build_object('from', old.status, 'to', new.status));
  end if;
  return new;
end;
$$;

drop trigger if exists applications_status_audit on public.applications;
create trigger applications_status_audit after update of status on public.applications
for each row execute function public.audit_workflow_status_change();

drop trigger if exists interviews_status_audit on public.interviews;
create trigger interviews_status_audit after update of status on public.interviews
for each row execute function public.audit_workflow_status_change();

drop trigger if exists offers_status_audit on public.offers;
create trigger offers_status_audit after update of status on public.offers
for each row execute function public.audit_workflow_status_change();

drop trigger if exists placements_status_audit on public.placements;
create trigger placements_status_audit after update of status on public.placements
for each row execute function public.audit_workflow_status_change();

revoke all on function public.audit_workflow_status_change() from public;
