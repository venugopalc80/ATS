-- Append-only subscription lifecycle history for support and auditability.
create table if not exists public.organization_subscription_history (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  subscription_id uuid references public.organization_subscriptions(id) on delete set null,
  actor_user_id uuid references public.profiles(id) on delete set null,
  event_type text not null check (event_type in ('created','plan_changed','trial_started','activated','payment_failed','paused','resumed','cancellation_scheduled','canceled','renewed','reconciled')),
  previous_state jsonb not null default '{}'::jsonb,
  new_state jsonb not null default '{}'::jsonb,
  source text not null check (source in ('customer_action','provider_webhook','admin_action','reconciliation','system')),
  created_at timestamptz not null default now()
);
create index if not exists organization_subscription_history_org_created_idx
  on public.organization_subscription_history(organization_id, created_at desc);
alter table public.organization_subscription_history enable row level security;
create policy organization_subscription_history_admin_read
  on public.organization_subscription_history for select to authenticated
  using (public.is_org_admin(organization_id));
revoke insert, update, delete on public.organization_subscription_history from anon, authenticated;
grant select on public.organization_subscription_history to authenticated;
