-- AQERITH Section 4, Ideas 18–21: search, talent pools, imports, campaigns.
-- Additive migration. Apply to staging only after review; do not apply to production from this branch.
-- All tenant-owned records carry organization_id. Browser clients receive read-only grants;
-- mutations are expected to pass through authenticated FastAPI handlers.

create table if not exists public.saved_searches (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  owner_user_id uuid not null references public.profiles(id) on delete cascade,
  name text not null check (length(trim(name)) between 1 and 120),
  record_type text not null check (record_type in ('candidates','applications','jobs','documents')),
  criteria_version integer not null default 1 check (criteria_version > 0),
  criteria jsonb not null default '{}'::jsonb check (jsonb_typeof(criteria) = 'object'),
  is_shared boolean not null default false,
  alerts_enabled boolean not null default false,
  last_alerted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, id)
);
create index if not exists saved_searches_owner_idx
  on public.saved_searches (organization_id, owner_user_id, updated_at desc);
create index if not exists saved_searches_shared_idx
  on public.saved_searches (organization_id, record_type, updated_at desc)
  where is_shared;

create table if not exists public.talent_pools (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  name text not null check (length(trim(name)) between 1 and 120),
  description text,
  owner_user_id uuid references public.profiles(id) on delete set null,
  visibility text not null default 'restricted' check (visibility in ('restricted','organisation')),
  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, id),
  unique (organization_id, name)
);
create index if not exists talent_pools_org_updated_idx
  on public.talent_pools (organization_id, updated_at desc);

create table if not exists public.talent_pool_memberships (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  pool_id uuid not null,
  candidate_id uuid not null,
  status text not null default 'active' check (status in ('active','removed','expired','withdrawn')),
  added_by uuid references public.profiles(id) on delete set null,
  purpose text,
  added_at timestamptz not null default now(),
  expires_at timestamptz,
  removed_at timestamptz,
  updated_at timestamptz not null default now(),
  foreign key (organization_id, pool_id) references public.talent_pools(organization_id, id) on delete cascade,
  foreign key (candidate_id) references public.candidates(id) on delete cascade,
  check (expires_at is null or expires_at > added_at),
  check ((status = 'active' and removed_at is null) or status <> 'active'),
  unique (organization_id, id)
);
create unique index if not exists talent_pool_memberships_active_unique
  on public.talent_pool_memberships (organization_id, pool_id, candidate_id)
  where status = 'active';
create index if not exists talent_pool_memberships_candidate_idx
  on public.talent_pool_memberships (organization_id, candidate_id, status);
create index if not exists talent_pool_memberships_pool_idx
  on public.talent_pool_memberships (organization_id, pool_id, status, added_at desc);

create table if not exists public.talent_pool_membership_events (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  membership_id uuid not null,
  actor_user_id uuid references public.profiles(id) on delete set null,
  event_type text not null check (event_type in ('added','updated','removed','expired','withdrawn','restored')),
  reason text,
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default now(),
  foreign key (organization_id, membership_id) references public.talent_pool_memberships(organization_id, id) on delete cascade
);
create index if not exists talent_pool_membership_events_idx
  on public.talent_pool_membership_events (organization_id, membership_id, created_at desc);

create table if not exists public.candidate_sources (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  source_key text not null,
  display_name text not null check (length(trim(display_name)) between 1 and 120),
  source_type text not null check (source_type in ('manual','csv_import','cv_import','referral','campaign','integration','job_board','other')),
  created_at timestamptz not null default now(),
  unique (organization_id, id),
  unique (organization_id, source_key)
);
create index if not exists candidate_sources_org_type_idx
  on public.candidate_sources (organization_id, source_type, display_name);

create table if not exists public.import_batches (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  source_id uuid,
  uploaded_by uuid references public.profiles(id) on delete set null,
  original_filename text not null check (length(trim(original_filename)) between 1 and 255),
  content_type text not null,
  file_size_bytes bigint not null check (file_size_bytes > 0 and file_size_bytes <= 26214400),
  file_sha256 text check (file_sha256 is null or file_sha256 ~ '^[a-f0-9]{64}$'),
  status text not null default 'uploaded' check (status in ('uploaded','previewed','queued','processing','completed','completed_with_errors','failed','cancelled')),
  duplicate_policy text not null default 'review' check (duplicate_policy in ('review','skip','allow')),
  total_rows integer not null default 0 check (total_rows >= 0),
  valid_rows integer not null default 0 check (valid_rows >= 0),
  imported_rows integer not null default 0 check (imported_rows >= 0),
  duplicate_rows integer not null default 0 check (duplicate_rows >= 0),
  rejected_rows integer not null default 0 check (rejected_rows >= 0),
  storage_bucket text,
  storage_path text,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  updated_at timestamptz not null default now(),
  foreign key (organization_id, source_id) references public.candidate_sources(organization_id, id) on delete set null,
  unique (organization_id, id)
);
create index if not exists import_batches_org_created_idx
  on public.import_batches (organization_id, created_at desc);
create index if not exists import_batches_status_idx
  on public.import_batches (status, created_at) where status in ('uploaded','queued','processing');

create table if not exists public.import_row_results (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  batch_id uuid not null,
  row_number integer not null check (row_number > 0),
  status text not null check (status in ('pending','valid','imported','duplicate','rejected','failed')),
  mapped_data jsonb not null default '{}'::jsonb check (jsonb_typeof(mapped_data) = 'object'),
  errors jsonb not null default '[]'::jsonb check (jsonb_typeof(errors) = 'array'),
  candidate_id uuid references public.candidates(id) on delete set null,
  duplicate_candidate_id uuid references public.candidates(id) on delete set null,
  processed_at timestamptz,
  created_at timestamptz not null default now(),
  foreign key (organization_id, batch_id) references public.import_batches(organization_id, id) on delete cascade,
  unique (organization_id, batch_id, row_number)
);
create index if not exists import_row_results_batch_status_idx
  on public.import_row_results (organization_id, batch_id, status, row_number);

create table if not exists public.recruitment_campaigns (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  name text not null check (length(trim(name)) between 1 and 160),
  description text,
  status text not null default 'draft' check (status in ('draft','scheduled','active','paused','completed','cancelled')),
  target_job_id uuid references public.jobs(id) on delete set null,
  owner_user_id uuid references public.profiles(id) on delete set null,
  starts_at timestamptz,
  ends_at timestamptz,
  budget_amount numeric(12,2) check (budget_amount is null or budget_amount >= 0),
  budget_currency char(3),
  attribution_window_days integer not null default 30 check (attribution_window_days between 1 and 365),
  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, id),
  check (ends_at is null or starts_at is null or ends_at > starts_at),
  check ((budget_amount is null and budget_currency is null) or (budget_amount is not null and budget_currency ~ '^[A-Z]{3}$'))
);
create index if not exists recruitment_campaigns_org_status_idx
  on public.recruitment_campaigns (organization_id, status, starts_at desc);

create table if not exists public.campaign_channels (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  campaign_id uuid not null,
  channel_key text not null check (channel_key in ('employee_referral','careers_site','linkedin','job_board','agency','event','email','social','other')),
  source_label text,
  external_reference text,
  spend_amount numeric(12,2) check (spend_amount is null or spend_amount >= 0),
  created_at timestamptz not null default now(),
  foreign key (organization_id, campaign_id) references public.recruitment_campaigns(organization_id, id) on delete cascade,
  unique (organization_id, id),
  unique (organization_id, campaign_id, channel_key, source_label)
);
create index if not exists campaign_channels_campaign_idx
  on public.campaign_channels (organization_id, campaign_id);

create table if not exists public.referrals (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  campaign_id uuid,
  channel_id uuid,
  candidate_id uuid references public.candidates(id) on delete set null,
  application_id uuid references public.applications(id) on delete set null,
  referrer_user_id uuid references public.profiles(id) on delete set null,
  referrer_name text,
  status text not null default 'received' check (status in ('received','reviewing','qualified','interviewing','hired','declined','withdrawn')),
  notes text,
  received_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  created_by uuid references public.profiles(id) on delete set null,
  unique (organization_id, id),
  foreign key (organization_id, campaign_id) references public.recruitment_campaigns(organization_id, id) on delete set null,
  foreign key (organization_id, channel_id) references public.campaign_channels(organization_id, id) on delete set null
);
create index if not exists referrals_org_status_idx
  on public.referrals (organization_id, status, received_at desc);
create index if not exists referrals_candidate_idx
  on public.referrals (organization_id, candidate_id, received_at desc);

create table if not exists public.campaign_memberships (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  campaign_id uuid not null,
  candidate_id uuid not null references public.candidates(id) on delete cascade,
  application_id uuid references public.applications(id) on delete set null,
  channel_id uuid,
  attribution_type text not null default 'first_touch' check (attribution_type in ('first_touch','last_touch','assisted','manual')),
  attributed_at timestamptz not null default now(),
  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  foreign key (organization_id, campaign_id) references public.recruitment_campaigns(organization_id, id) on delete cascade,
  foreign key (organization_id, channel_id) references public.campaign_channels(organization_id, id) on delete set null,
  unique (organization_id, campaign_id, candidate_id, attribution_type)
);
create index if not exists campaign_memberships_campaign_idx
  on public.campaign_memberships (organization_id, campaign_id, attributed_at desc);
create index if not exists campaign_memberships_candidate_idx
  on public.campaign_memberships (organization_id, candidate_id, attributed_at desc);

create table if not exists public.campaign_events (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  campaign_id uuid not null,
  candidate_id uuid references public.candidates(id) on delete set null,
  application_id uuid references public.applications(id) on delete set null,
  actor_user_id uuid references public.profiles(id) on delete set null,
  event_type text not null check (event_type in ('created','updated','activated','paused','completed','referral_received','qualified','interview','hired','status_corrected')),
  previous_value jsonb,
  new_value jsonb,
  reason text,
  occurred_at timestamptz not null default now(),
  foreign key (organization_id, campaign_id) references public.recruitment_campaigns(organization_id, id) on delete cascade
);
create index if not exists campaign_events_campaign_time_idx
  on public.campaign_events (organization_id, campaign_id, occurred_at desc);

-- Tenant ownership checks are explicit on membership writes. Candidate/application/job records
-- must exist inside the same organisation; a row-level policy alone is not enough for link integrity.
create or replace function public.validate_aqerith_sourcing_links()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if tg_table_name = 'talent_pool_memberships' then
    if not exists (select 1 from public.candidates c where c.id = new.candidate_id and c.organization_id = new.organization_id) then
      raise exception 'Candidate must belong to the same organisation' using errcode = '23514';
    end if;
  elsif tg_table_name = 'recruitment_campaigns' then
    if new.target_job_id is not null and not exists (select 1 from public.jobs j where j.id = new.target_job_id and j.organization_id = new.organization_id) then
      raise exception 'Target job must belong to the same organisation' using errcode = '23514';
    end if;
  elsif tg_table_name = 'referrals' then
    if new.candidate_id is not null and not exists (select 1 from public.candidates c where c.id = new.candidate_id and c.organization_id = new.organization_id) then
      raise exception 'Referral candidate must belong to the same organisation' using errcode = '23514';
    end if;
    if new.application_id is not null and not exists (select 1 from public.applications a where a.id = new.application_id and a.organization_id = new.organization_id) then
      raise exception 'Referral application must belong to the same organisation' using errcode = '23514';
    end if;
  elsif tg_table_name = 'campaign_memberships' then
    if not exists (select 1 from public.candidates c where c.id = new.candidate_id and c.organization_id = new.organization_id) then
      raise exception 'Campaign candidate must belong to the same organisation' using errcode = '23514';
    end if;
    if new.application_id is not null and not exists (select 1 from public.applications a where a.id = new.application_id and a.organization_id = new.organization_id and a.candidate_id = new.candidate_id) then
      raise exception 'Campaign application must match the candidate and organisation' using errcode = '23514';
    end if;
  elsif tg_table_name = 'import_row_results' then
    if new.candidate_id is not null and not exists (select 1 from public.candidates c where c.id = new.candidate_id and c.organization_id = new.organization_id) then
      raise exception 'Imported candidate must belong to the same organisation' using errcode = '23514';
    end if;
    if new.duplicate_candidate_id is not null and not exists (select 1 from public.candidates c where c.id = new.duplicate_candidate_id and c.organization_id = new.organization_id) then
      raise exception 'Duplicate candidate must belong to the same organisation' using errcode = '23514';
    end if;
  end if;
  return new;
end;
$$;

drop trigger if exists talent_pool_memberships_validate_org on public.talent_pool_memberships;
create trigger talent_pool_memberships_validate_org before insert or update on public.talent_pool_memberships
for each row execute function public.validate_aqerith_sourcing_links();
drop trigger if exists recruitment_campaigns_validate_org on public.recruitment_campaigns;
create trigger recruitment_campaigns_validate_org before insert or update on public.recruitment_campaigns
for each row execute function public.validate_aqerith_sourcing_links();
drop trigger if exists referrals_validate_org on public.referrals;
create trigger referrals_validate_org before insert or update on public.referrals
for each row execute function public.validate_aqerith_sourcing_links();
drop trigger if exists campaign_memberships_validate_org on public.campaign_memberships;
create trigger campaign_memberships_validate_org before insert or update on public.campaign_memberships
for each row execute function public.validate_aqerith_sourcing_links();
drop trigger if exists import_row_results_validate_org on public.import_row_results;
create trigger import_row_results_validate_org before insert or update on public.import_row_results
for each row execute function public.validate_aqerith_sourcing_links();

-- Membership history is append-only for ordinary browser roles.
create or replace function public.prevent_sourcing_history_mutation()
returns trigger language plpgsql set search_path = public, pg_temp as $$
begin
  raise exception 'Sourcing history is append-only' using errcode = '42501';
end;
$$;
drop trigger if exists talent_pool_membership_events_append_only on public.talent_pool_membership_events;
create trigger talent_pool_membership_events_append_only before update or delete on public.talent_pool_membership_events
for each row execute function public.prevent_sourcing_history_mutation();
drop trigger if exists campaign_events_append_only on public.campaign_events;
create trigger campaign_events_append_only before update or delete on public.campaign_events
for each row execute function public.prevent_sourcing_history_mutation();

do $$
declare t text;
begin
  foreach t in array array[
    'saved_searches','talent_pools','talent_pool_memberships','talent_pool_membership_events',
    'candidate_sources','import_batches','import_row_results','recruitment_campaigns',
    'campaign_channels','referrals','campaign_memberships','campaign_events'
  ] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists %I on public.%I', t || '_member_read', t);
    execute format('create policy %I on public.%I for select to authenticated using (public.is_org_member(organization_id))', t || '_member_read', t);
  end loop;
end $$;

drop policy if exists saved_searches_owner_or_shared on public.saved_searches;
create policy saved_searches_owner_or_shared on public.saved_searches
  for select to authenticated
  using (public.is_org_member(organization_id) and (owner_user_id = auth.uid() or is_shared));

revoke all on public.saved_searches, public.talent_pools, public.talent_pool_memberships,
  public.talent_pool_membership_events, public.candidate_sources, public.import_batches,
  public.import_row_results, public.recruitment_campaigns, public.campaign_channels,
  public.referrals, public.campaign_memberships, public.campaign_events from anon;
grant select on public.saved_searches, public.talent_pools, public.talent_pool_memberships,
  public.talent_pool_membership_events, public.candidate_sources, public.import_batches,
  public.import_row_results, public.recruitment_campaigns, public.campaign_channels,
  public.referrals, public.campaign_memberships, public.campaign_events to authenticated;
