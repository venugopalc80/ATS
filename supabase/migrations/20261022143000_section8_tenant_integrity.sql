-- Section 8 follow-up hardening: enforce tenant-consistent references and rights-request transitions
-- at the database boundary, including service-role/API writes that bypass RLS.

create or replace function public.validate_section8_tenant_integrity()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  referenced_org uuid;
begin
  if tg_table_name = 'candidate_processing_records' then
    select organization_id into referenced_org
      from public.candidates where id = new.candidate_id;
    if referenced_org is null or referenced_org <> new.organization_id then
      raise exception 'candidate must belong to the same organization'
        using errcode = '23514';
    end if;

    if new.notice_id is not null then
      select organization_id into referenced_org
        from public.privacy_notices where id = new.notice_id;
      if referenced_org is null or referenced_org <> new.organization_id then
        raise exception 'privacy notice must belong to the same organization'
          using errcode = '23514';
      end if;
    end if;

  elsif tg_table_name = 'privacy_rights_requests' then
    if new.candidate_id is not null then
      select organization_id into referenced_org
        from public.candidates where id = new.candidate_id;
      if referenced_org is null or referenced_org <> new.organization_id then
        raise exception 'candidate must belong to the same organization'
          using errcode = '23514';
      end if;
    end if;

  elsif tg_table_name = 'retention_exceptions' then
    if new.policy_id is not null then
      select organization_id into referenced_org
        from public.retention_policies where id = new.policy_id;
      if referenced_org is null or referenced_org <> new.organization_id then
        raise exception 'retention policy must belong to the same organization'
          using errcode = '23514';
      end if;
    end if;

    referenced_org := null;
    case new.target_table
      when 'candidates' then
        select organization_id into referenced_org from public.candidates where id = new.target_record_id;
      when 'applications' then
        select organization_id into referenced_org from public.applications where id = new.target_record_id;
      when 'candidate_documents' then
        select organization_id into referenced_org from public.candidate_documents where id = new.target_record_id;
      when 'candidate_processing_records' then
        select organization_id into referenced_org from public.candidate_processing_records where id = new.target_record_id;
      when 'audit_events' then
        select organization_id into referenced_org from public.audit_events where id = new.target_record_id;
      else
        raise exception 'unsupported retention target table'
          using errcode = '23514';
    end case;
    if referenced_org is null or referenced_org <> new.organization_id then
      raise exception 'retention target must belong to the same organization'
        using errcode = '23514';
    end if;

  elsif tg_table_name = 'webhook_subscriptions' then
    if new.integration_id is not null then
      select organization_id into referenced_org
        from public.integration_connections where id = new.integration_id;
      if referenced_org is null or referenced_org <> new.organization_id then
        raise exception 'integration must belong to the same organization'
          using errcode = '23514';
      end if;
    end if;

  elsif tg_table_name = 'webhook_delivery_attempts' then
    select organization_id into referenced_org
      from public.webhook_subscriptions where id = new.subscription_id;
    if referenced_org is null or referenced_org <> new.organization_id then
      raise exception 'webhook subscription must belong to the same organization'
        using errcode = '23514';
    end if;
  end if;

  return new;
end;
$$;

create trigger candidate_processing_tenant_integrity
  before insert or update of organization_id, candidate_id, notice_id
  on public.candidate_processing_records
  for each row execute function public.validate_section8_tenant_integrity();

create trigger privacy_rights_request_tenant_integrity
  before insert or update of organization_id, candidate_id
  on public.privacy_rights_requests
  for each row execute function public.validate_section8_tenant_integrity();

create trigger retention_exception_tenant_integrity
  before insert or update of organization_id, policy_id, target_table, target_record_id
  on public.retention_exceptions
  for each row execute function public.validate_section8_tenant_integrity();

create trigger webhook_subscription_tenant_integrity
  before insert or update of organization_id, integration_id
  on public.webhook_subscriptions
  for each row execute function public.validate_section8_tenant_integrity();

create trigger webhook_delivery_tenant_integrity
  before insert or update of organization_id, subscription_id
  on public.webhook_delivery_attempts
  for each row execute function public.validate_section8_tenant_integrity();


create or replace function public.enforce_privacy_request_transitions()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  transition_allowed boolean := false;
begin
  if new.status is not distinct from old.status then
    return new;
  end if;

  transition_allowed := case old.status
    when 'received' then new.status in ('identity_verification', 'cancelled')
    when 'identity_verification' then new.status in ('in_progress', 'awaiting_information', 'declined', 'cancelled')
    when 'in_progress' then new.status in ('awaiting_information', 'partially_completed', 'completed', 'declined', 'cancelled')
    when 'awaiting_information' then new.status in ('in_progress', 'cancelled')
    when 'partially_completed' then new.status in ('in_progress', 'completed', 'declined', 'cancelled')
    else false
  end;

  if not transition_allowed then
    raise exception 'invalid privacy request status transition: % -> %', old.status, new.status
      using errcode = '23514';
  end if;

  if new.status in ('partially_completed', 'declined')
     and nullif(btrim(coalesce(new.exception_details, '')), '') is null
     and nullif(btrim(coalesce(new.retention_justification, '')), '') is null then
    raise exception 'partial completion or decline requires documented justification'
      using errcode = '23514';
  end if;

  if new.status in ('partially_completed', 'completed', 'declined', 'cancelled') then
    new.completed_at := coalesce(new.completed_at, now());
  else
    new.completed_at := null;
  end if;

  return new;
end;
$$;

create trigger privacy_request_status_transition_guard
  before update of status on public.privacy_rights_requests
  for each row execute function public.enforce_privacy_request_transitions();

revoke all on function public.validate_section8_tenant_integrity() from public;
revoke all on function public.enforce_privacy_request_transitions() from public;
