-- Make the absence of browser access to webhook events explicit for RLS advisors.
drop policy if exists billing_webhook_events_deny_browser on public.billing_webhook_events;
create policy billing_webhook_events_deny_browser
  on public.billing_webhook_events
  for all to anon, authenticated
  using (false)
  with check (false);
