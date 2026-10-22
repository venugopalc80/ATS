-- AQERITH Ideas 14–15: communication and notification foundations.
-- Additive only. Candidate-facing delivery is intentionally not enabled until a provider worker
-- and authenticated provider webhook verification are configured.

create table if not exists public.communication_threads (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  application_id uuid not null references public.applications(id) on delete cascade,
  candidate_id uuid not null references public.candidates(id) on delete cascade,
  subject text,
  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, id)
);

create index if not exists communication_threads_application_idx
  on public.communication_threads (organization_id, application_id, created_at desc);
create index if not exists communication_threads_candidate_idx
  on public.communication_threads (organization_id, candidate_id, created_at desc);

create table if not exists public.message_templates (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  template_key text not null,
  version integer not null check (version > 0),
  name text not null,
  channel text not null check (channel in ('email','sms','in_app')),
  subject text,
  body_text text not null check (length(trim(body_text)) > 0),
  status text not null default 'draft' check (status in ('draft','approved','retired')),
  created_by uuid references public.profiles(id) on delete set null,
  approved_by uuid references public.profiles(id) on delete set null,
  approved_at timestamptz,
  created_at timestamptz not null default now(),
  unique (organization_id, template_key, version),
  check ((status = 'approved' and approved_at is not null and approved_by is not null)
      or status <> 'approved')
);
create index if not exists message_templates_org_status_idx
  on public.message_templates (organization_id, status, name);

create table if not exists public.messages (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  thread_id uuid not null,
  sender_user_id uuid references public.profiles(id) on delete set null,
  visibility text not null check (visibility in ('candidate','internal')),
  channel text not null check (channel in ('email','sms','in_app','internal')),
  body_text text not null check (length(trim(body_text)) > 0),
  subject text,
  template_id uuid references public.message_templates(id) on delete set null,
  template_version integer,
  status text not null default 'draft'
    check (status in ('internal','draft','queued','sent','delivered','failed','bounced','undelivered')),
  idempotency_key text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (organization_id, thread_id)
    references public.communication_threads(organization_id, id) on delete cascade,
  check (
    (visibility = 'internal' and channel = 'internal' and status = 'internal')
    or
    (visibility = 'candidate' and channel <> 'internal' and status <> 'internal')
  ),
  check ((template_id is null and template_version is null) or
         (template_id is not null and template_version is not null and template_version > 0))
);
create unique index if not exists messages_org_idempotency_idx
  on public.messages (organization_id, idempotency_key)
  where idempotency_key is not null;
create index if not exists messages_thread_created_idx
  on public.messages (organization_id, thread_id, created_at asc);

create table if not exists public.message_recipients (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  message_id uuid not null references public.messages(id) on delete cascade,
  recipient_type text not null default 'to' check (recipient_type in ('to','cc','bcc')),
  recipient_address text not null,
  delivery_status text not null default 'pending'
    check (delivery_status in ('pending','queued','sent','delivered','failed','bounced','undelivered')),
  created_at timestamptz not null default now(),
  foreign key (organization_id, message_id)
    references public.messages(organization_id, id) on delete cascade
);
create index if not exists message_recipients_message_idx
  on public.message_recipients (organization_id, message_id);

create table if not exists public.delivery_events (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  message_id uuid not null references public.messages(id) on delete cascade,
  recipient_id uuid references public.message_recipients(id) on delete set null,
  provider text not null,
  provider_event_id text,
  event_type text not null check (event_type in ('queued','sent','delivered','opened','bounced','failed','undelivered')),
  occurred_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  foreign key (organization_id, message_id)
    references public.messages(organization_id, id) on delete cascade,
  unique (provider, provider_event_id)
);
create index if not exists delivery_events_message_time_idx
  on public.delivery_events (organization_id, message_id, occurred_at desc);

create table if not exists public.notification_preferences (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid not null references public.profiles(id) on delete cascade,
  notification_type text not null,
  channel text not null check (channel in ('in_app','email','sms')),
  enabled boolean not null default true,
  updated_at timestamptz not null default now(),
  unique (organization_id, user_id, notification_type, channel)
);
create index if not exists notification_preferences_user_idx
  on public.notification_preferences (organization_id, user_id);

create table if not exists public.notification_events (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  notification_type text not null,
  subject_user_id uuid references public.profiles(id) on delete set null,
  payload jsonb not null default '{}'::jsonb,
  essential boolean not null default false,
  idempotency_key text not null,
  created_at timestamptz not null default now(),
  unique (organization_id, idempotency_key)
);
create index if not exists notification_events_org_created_idx
  on public.notification_events (organization_id, created_at desc);

create table if not exists public.notification_deliveries (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  notification_event_id uuid not null references public.notification_events(id) on delete cascade,
  channel text not null check (channel in ('in_app','email','sms')),
  recipient_address text,
  status text not null default 'pending'
    check (status in ('pending','queued','sent','delivered','failed','bounced','undelivered','read','skipped')),
  attempt_count integer not null default 0 check (attempt_count >= 0),
  next_attempt_at timestamptz,
  provider_message_id text,
  last_error_code text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (organization_id, notification_event_id)
    references public.notification_events(organization_id, id) on delete cascade,
  unique (notification_event_id, channel, recipient_address)
);
create index if not exists notification_deliveries_retry_idx
  on public.notification_deliveries (status, next_attempt_at)
  where status in ('pending','queued','failed');

-- RLS is mandatory on every tenant-owned table. Policy predicates bind each row to membership.
do $$
declare t text;
begin
  foreach t in array array[
    'communication_threads','message_templates','messages','message_recipients',
    'delivery_events','notification_preferences','notification_events','notification_deliveries'
  ] loop
    execute format('alter table public.%I enable row level security', t);
  end loop;
end $$;

drop policy if exists communication_threads_member_all on public.communication_threads;
create policy communication_threads_member_all on public.communication_threads
  for all to authenticated
  using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));

drop policy if exists message_templates_member_all on public.message_templates;
create policy message_templates_member_all on public.message_templates
  for all to authenticated
  using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));

drop policy if exists messages_member_all on public.messages;
create policy messages_member_all on public.messages
  for all to authenticated
  using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));

drop policy if exists message_recipients_member_all on public.message_recipients;
create policy message_recipients_member_all on public.message_recipients
  for all to authenticated
  using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));

drop policy if exists delivery_events_member_read on public.delivery_events;
create policy delivery_events_member_read on public.delivery_events
  for select to authenticated
  using (public.is_org_member(organization_id));

drop policy if exists notification_preferences_self_all on public.notification_preferences;
create policy notification_preferences_self_all on public.notification_preferences
  for all to authenticated
  using (user_id = auth.uid() and public.is_org_member(organization_id))
  with check (user_id = auth.uid() and public.is_org_member(organization_id));

drop policy if exists notification_events_member_read on public.notification_events;
create policy notification_events_member_read on public.notification_events
  for select to authenticated
  using (public.is_org_member(organization_id));

drop policy if exists notification_deliveries_member_read on public.notification_deliveries;
create policy notification_deliveries_member_read on public.notification_deliveries
  for select to authenticated
  using (public.is_org_member(organization_id));

revoke all on public.communication_threads, public.message_templates, public.messages,
  public.message_recipients, public.delivery_events, public.notification_preferences,
  public.notification_events, public.notification_deliveries from anon;

grant select, insert, update on public.communication_threads, public.message_templates,
  public.messages, public.message_recipients, public.notification_preferences to authenticated;
grant select on public.delivery_events, public.notification_events,
  public.notification_deliveries to authenticated;


-- Enforce the application/candidate relationship even for direct authenticated inserts.
create or replace function public.validate_communication_thread_links()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  if not exists (
    select 1
    from public.applications a
    join public.candidates c
      on c.id = a.candidate_id
     and c.organization_id = a.organization_id
    where a.id = new.application_id
      and a.organization_id = new.organization_id
      and a.candidate_id = new.candidate_id
  ) then
    raise exception 'Application and candidate must belong to the same organisation and match'
      using errcode = '23514';
  end if;
  return new;
end;
$$;

drop trigger if exists communication_threads_validate_links on public.communication_threads;
create trigger communication_threads_validate_links
before insert or update of organization_id, application_id, candidate_id
on public.communication_threads
for each row execute function public.validate_communication_thread_links();
