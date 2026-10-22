-- Tighten consent evidence invariants at the database boundary.
-- API validation remains useful for friendly errors; these constraints protect direct writes too.

alter table public.candidate_processing_records
  add constraint candidate_processing_consent_evidence_complete
  check (
    (
      legal_basis = 'consent'
      and consent_status is not null
      and consent_status in ('granted', 'withdrawn')
      and consent_captured_at is not null
      and (consent_status <> 'withdrawn' or consent_withdrawn_at is not null)
      and (consent_withdrawn_at is null or consent_withdrawn_at >= consent_captured_at)
    )
    or
    (
      legal_basis <> 'consent'
      and (consent_status is null or consent_status = 'not_applicable')
      and consent_captured_at is null
      and consent_withdrawn_at is null
    )
  );

-- A completed timestamp is only meaningful for terminal workflow states.
alter table public.privacy_rights_requests
  add constraint privacy_rights_completed_timestamp_consistent
  check (
    (status in ('partially_completed', 'completed', 'declined', 'cancelled') and completed_at is not null)
    or
    (status not in ('partially_completed', 'completed', 'declined', 'cancelled') and completed_at is null)
  );
