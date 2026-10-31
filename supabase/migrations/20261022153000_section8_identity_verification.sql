-- Add auditable identity-verification evidence before a privacy request enters processing.
alter table public.privacy_rights_requests
  add column identity_verification_method text
    check (identity_verification_method in ('existing_account','email_challenge','document_review','other')),
  add column identity_verified_at timestamptz,
  add column identity_verified_by uuid references public.profiles(id) on delete set null,
  add constraint privacy_request_identity_verification_evidence_complete
    check (
      (identity_verification_method is null and identity_verified_at is null and identity_verified_by is null)
      or
      (identity_verification_method is not null and identity_verified_at is not null and identity_verified_by is not null)
    );

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

  if old.status = 'identity_verification' and new.status = 'in_progress'
     and (new.identity_verification_method is null
          or new.identity_verified_at is null
          or new.identity_verified_by is null) then
    raise exception 'identity verification evidence is required before processing'
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

revoke all on function public.enforce_privacy_request_transitions() from public;
