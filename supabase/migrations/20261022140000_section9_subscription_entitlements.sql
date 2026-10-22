-- AQERITH Section 9 / Idea 46: subscription and entitlement foundation.
-- Provider events store a digest and operational metadata, not raw webhook payloads.
-- Do not add provider secrets or cardholder data to these tables.

create table if not exists public.subscription_plans (
  id uuid primary key default gen_random_uuid(),
  plan_key text not null unique check (plan_key ~ '^[a-z][a-z0-9_-]{1,49}$'),
  display_name text not null check (length(trim(display_name)) between 2 and 100),
  description text,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.plan_entitlements (
  plan_id uuid not null references public.subscription_plans(id) on delete cascade,
  entitlement_key text not null check (entitlement_key ~ '^[a-z][a-z0-9_.-]{1,99}$'),
  entitlement_value jsonb not null,
  updated_at timestamptz not null default now(),
  primary key (plan_id, entitlement_key),
  check (jsonb_typeof(entitlement_value) in ('boolean', 'number', 'null'))
);

create table if not exists public.organization_subscriptions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  plan_id uuid not null references public.subscription_plans(id) on delete restrict,
  status text not null default 'incomplete'
    check (status in ('incomplete','trialing','active','past_due','paused','canceled','unpaid')),
  billing_provider text check (billing_provider in ('stripe')),
  provider_customer_id text,
  provider_subscription_id text,
  current_period_start timestamptz,
  current_period_end timestamptz,
  trial_ends_at timestamptz,
  cancel_at_period_end boolean not null default false,
  canceled_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  created_by uuid references public.profiles(id) on delete set null,
  constraint organization_subscriptions_period_check
    check (current_period_end is null or current_period_start is null or current_period_end > current_period_start),
  constraint organization_subscriptions_provider_pair_check
    check ((billing_provider is null and provider_subscription_id is null)
        or (billing_provider is not null and provider_subscription_id is not null))
);

create unique index if not exists organization_subscriptions_provider_sub_uq
  on public.organization_subscriptions(billing_provider, provider_subscription_id)
  where provider_subscription_id is not null;

create unique index if not exists organization_subscriptions_one_current_per_org_uq
  on public.organization_subscriptions(organization_id)
  where status in ('incomplete','trialing','active','past_due','paused','unpaid');

create index if not exists organization_subscriptions_org_status_idx
  on public.organization_subscriptions(organization_id, status);

create table if not exists public.billing_webhook_events (
  id uuid primary key default gen_random_uuid(),
  billing_provider text not null check (billing_provider in ('stripe')),
  provider_event_id text not null,
  event_type text not null,
  organization_id uuid references public.organizations(id) on delete set null,
  payload_sha256 text not null check (payload_sha256 ~ '^[a-f0-9]{64}$'),
  processing_status text not null default 'received'
    check (processing_status in ('received','processing','processed','failed','ignored')),
  received_at timestamptz not null default now(),
  processed_at timestamptz,
  failure_code text,
  unique (billing_provider, provider_event_id)
);

create index if not exists billing_webhook_events_org_received_idx
  on public.billing_webhook_events(organization_id, received_at desc);

create table if not exists public.organization_usage_periods (
  organization_id uuid not null references public.organizations(id) on delete cascade,
  metric_key text not null check (metric_key ~ '^[a-z][a-z0-9_.-]{1,99}$'),
  period_start date not null,
  period_end date not null,
  quantity bigint not null default 0 check (quantity >= 0),
  updated_at timestamptz not null default now(),
  primary key (organization_id, metric_key, period_start),
  check (period_end > period_start)
);

create index if not exists organization_usage_periods_org_period_idx
  on public.organization_usage_periods(organization_id, period_start desc);

alter table public.subscription_plans enable row level security;
alter table public.plan_entitlements enable row level security;
alter table public.organization_subscriptions enable row level security;
alter table public.billing_webhook_events enable row level security;
alter table public.organization_usage_periods enable row level security;

drop policy if exists subscription_plans_authenticated_read on public.subscription_plans;
create policy subscription_plans_authenticated_read
  on public.subscription_plans for select to authenticated
  using (is_active or public.is_org_admin(null::uuid) = false);

drop policy if exists plan_entitlements_authenticated_read on public.plan_entitlements;
create policy plan_entitlements_authenticated_read
  on public.plan_entitlements for select to authenticated
  using (exists (
    select 1 from public.subscription_plans p
    where p.id = plan_id and p.is_active
  ));

drop policy if exists organization_subscriptions_admin_read on public.organization_subscriptions;
create policy organization_subscriptions_admin_read
  on public.organization_subscriptions for select to authenticated
  using (public.is_org_admin(organization_id));

drop policy if exists organization_usage_periods_admin_read on public.organization_usage_periods;
create policy organization_usage_periods_admin_read
  on public.organization_usage_periods for select to authenticated
  using (public.is_org_admin(organization_id));

-- No direct browser access to webhook ledger. Mutations are backend-only.
revoke all on public.billing_webhook_events from anon, authenticated;
revoke insert, update, delete on public.subscription_plans from anon, authenticated;
revoke insert, update, delete on public.plan_entitlements from anon, authenticated;
revoke insert, update, delete on public.organization_subscriptions from anon, authenticated;
revoke insert, update, delete on public.organization_usage_periods from anon, authenticated;

grant select on public.subscription_plans to authenticated;
grant select on public.plan_entitlements to authenticated;
grant select on public.organization_subscriptions to authenticated;
grant select on public.organization_usage_periods to authenticated;
