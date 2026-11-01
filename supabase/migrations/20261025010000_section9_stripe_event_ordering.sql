-- Section 9 / Idea 46: keep subscription state monotonic under out-of-order Stripe delivery.
-- Existing rows have no known event sequence; NULL allows the first new event to reconcile them.
alter table public.organization_subscriptions
  add column if not exists provider_event_created_at bigint;

comment on column public.organization_subscriptions.provider_event_created_at
  is 'Stripe event.created timestamp of the latest applied subscription event; used to reject stale webhook deliveries.';
