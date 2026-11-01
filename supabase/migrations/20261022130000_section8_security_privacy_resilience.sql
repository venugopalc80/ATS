-- Section 8: privacy, retention, security events, integrations and recovery evidence.
-- Additive migration: preserves existing candidate and audit data.

create table if not exists public.privacy_notices (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  version text not null,
  purpose text not null,
  notice_text text not null,
  effective_at timestamptz not null,
  retired_at timestamptz,
  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  unique (organization_id, purpose, version),
  check (retired_at is null or retired_at >= effective_at)
);

create table if not exists public.candidate_processing_records (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  candidate_id uuid not null references public.candidates(id) on delete restrict,
  purpose text not null,
  legal_basis text not null check (legal_basis in ('consent','contract','legal_obligation','legitimate_interests','public_task','vital_interests','other')),
  notice_id uuid references public.privacy_notices(id) on delete set null,
  consent_status text check (consent_status in ('granted','withdrawn','not_applicable')),
  consent_captured_at timestamptz,
  consent_withdrawn_at timestamptz,
  processing_preferences jsonb not null default '{}'::jsonb,
  recorded_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (
    (legal_basis = 'consent' and consent_status in ('granted','withdrawn') and consent_captured_at is not null)
    or (legal_basis <> 'consent' and (consent_status is null or consent_status = 'not_applicable'))
  ),
  check (consent_withdrawn_at is null or consent_withdrawn_at >= consent_captured_at)
);
create index if not exists candidate_processing_org_candidate_idx
  on public.candidate_processing_records (organization_id, candidate_id, purpose);

create table if not exists public.privacy_rights_requests (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  candidate_id uuid references public.candidates(id) on delete set null,
  request_type text not null check (request_type in ('access','correction','restriction','erasure','portability','objection','other')),
  status text not null default 'received' check (status in ('received','identity_verification','in_progress','awaiting_information','partially_completed','completed','declined','cancelled')),
  requester_email text,
  requested_scope jsonb not null default '{}'::jsonb,
  affected_systems jsonb not null default '[]'::jsonb,
  exception_details text,
  retention_justification text,
  received_at timestamptz not null default now(),
  due_at timestamptz,
  completed_at timestamptz,
  created_by uuid references public.profiles(id) on delete set null,
  updated_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (completed_at is null or status in ('partially_completed','completed','declined','cancelled'))
);
create index if not exists privacy_requests_org_status_idx
  on public.privacy_rights_requests (organization_id, status, received_at desc);
create index if not exists privacy_requests_candidate_idx
  on public.privacy_rights_requests (organization_id, candidate_id);

create table if not exists public.retention_policies (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  data_category text not null,
  purpose text not null,
  jurisdiction text not null check (jurisdiction in ('GB','US','IN','AU','GLOBAL')),
  retention_days integer not null check (retention_days >= 0),
  action text not null check (action in ('review','delete','anonymise')),
  version integer not null check (version > 0),
  enabled boolean not null default true,
  effective_at timestamptz not null default now(),
  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  unique (organization_id, data_category, purpose, jurisdiction, version)
);
create index if not exists retention_policies_active_idx
  on public.retention_policies (organization_id, enabled, data_category);

create table if not exists public.retention_exceptions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  policy_id uuid references public.retention_policies(id) on delete set null,
  target_table text not null,
  target_record_id uuid not null,
  exception_type text not null check (exception_type in ('legal_hold','legal_requirement','dispute','manual_review','other')),
  reason text not null,
  starts_at timestamptz not null default now(),
  ends_at timestamptz,
  approved_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  check (ends_at is null or ends_at > starts_at)
);
create index if not exists retention_exceptions_target_idx
  on public.retention_exceptions (organization_id, target_table, target_record_id);

create table if not exists public.retention_execution_logs (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  policy_id uuid references public.retention_policies(id) on delete set null,
  target_table text not null,
  target_record_id uuid not null,
  action text not null check (action in ('review','delete','anonymise','skipped')),
  status text not null check (status in ('queued','running','succeeded','failed','skipped')),
  idempotency_key text not null,
  exception_reason text,
  error_code text,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  unique (organization_id, idempotency_key)
);
create index if not exists retention_execution_org_status_idx
  on public.retention_execution_logs (organization_id, status, created_at desc);

-- Separate from general audit_events so security event access can be restricted more tightly.
create table if not exists public.security_events (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid references public.organizations(id) on delete set null,
  actor_user_id uuid references public.profiles(id) on delete set null,
  action text not null,
  target_type text,
  target_id uuid,
  outcome text not null check (outcome in ('success','failure','blocked','unknown')),
  source_service text not null default 'api',
  request_id text,
  ip_address inet,
  user_agent text,
  metadata jsonb not null default '{}'::jsonb,
  occurred_at timestamptz not null default now()
);
create index if not exists security_events_org_time_idx
  on public.security_events (organization_id, occurred_at desc);
create index if not exists security_events_action_time_idx
  on public.security_events (action, occurred_at desc);

create table if not exists public.integration_connections (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  provider text not null,
  display_name text not null,
  status text not null default 'disconnected' check (status in ('connected','degraded','disconnected','revoked','error')),
  granted_scopes text[] not null default '{}',
  credential_reference text,
  connected_by uuid references public.profiles(id) on delete set null,
  connected_at timestamptz,
  disconnected_at timestamptz,
  last_checked_at timestamptz,
  last_error_code text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, provider, display_name)
);

create table if not exists public.webhook_subscriptions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  integration_id uuid references public.integration_connections(id) on delete cascade,
  endpoint_url text not null,
  secret_reference text not null,
  event_types text[] not null,
  active boolean not null default true,
  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.webhook_delivery_attempts (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  subscription_id uuid not null references public.webhook_subscriptions(id) on delete cascade,
  event_id text not null,
  attempt_number integer not null check (attempt_number > 0),
  status text not null check (status in ('queued','delivered','failed','retrying','dead_letter')),
  response_status integer,
  error_code text,
  attempted_at timestamptz not null default now(),
  next_attempt_at timestamptz,
  unique (subscription_id, event_id, attempt_number)
);
create index if not exists webhook_delivery_status_idx
  on public.webhook_delivery_attempts (organization_id, status, attempted_at desc);

create table if not exists public.recovery_drills (
  id uuid primary key default gen_random_uuid(),
  environment text not null,
  drill_type text not null check (drill_type in ('database_restore','storage_restore','application_recovery','full_disaster_recovery')),
  status text not null check (status in ('planned','running','passed','failed','blocked')),
  recovery_point_objective_minutes integer,
  recovery_time_objective_minutes integer,
  observed_recovery_point_minutes integer,
  observed_recovery_time_minutes integer,
  runbook_reference text,
  findings jsonb not null default '{}'::jsonb,
  owner_user_id uuid references public.profiles(id) on delete set null,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now()
);

-- Tenant reads are scoped; sensitive administrative writes are performed through the
-- authenticated backend after explicit membership/role checks.
alter table public.privacy_notices enable row level security;
alter table public.candidate_processing_records enable row level security;
alter table public.privacy_rights_requests enable row level security;
alter table public.retention_policies enable row level security;
alter table public.retention_exceptions enable row level security;
alter table public.retention_execution_logs enable row level security;
alter table public.security_events enable row level security;
alter table public.integration_connections enable row level security;
alter table public.webhook_subscriptions enable row level security;
alter table public.webhook_delivery_attempts enable row level security;
alter table public.recovery_drills enable row level security;

create policy privacy_notices_member_read on public.privacy_notices
  for select to authenticated using (public.is_org_member(organization_id));
create policy candidate_processing_member_read on public.candidate_processing_records
  for select to authenticated using (public.is_org_member(organization_id));
create policy privacy_requests_admin_read on public.privacy_rights_requests
  for select to authenticated using (public.is_org_admin(organization_id));
create policy retention_policies_admin_read on public.retention_policies
  for select to authenticated using (public.is_org_admin(organization_id));
create policy retention_exceptions_admin_read on public.retention_exceptions
  for select to authenticated using (public.is_org_admin(organization_id));
create policy retention_logs_admin_read on public.retention_execution_logs
  for select to authenticated using (public.is_org_admin(organization_id));
create policy security_events_admin_read on public.security_events
  for select to authenticated using (organization_id is not null and public.is_org_admin(organization_id));
create policy integrations_admin_read on public.integration_connections
  for select to authenticated using (public.is_org_admin(organization_id));
create policy webhooks_admin_read on public.webhook_subscriptions
  for select to authenticated using (public.is_org_admin(organization_id));
create policy webhook_attempts_admin_read on public.webhook_delivery_attempts
  for select to authenticated using (public.is_org_admin(organization_id));
