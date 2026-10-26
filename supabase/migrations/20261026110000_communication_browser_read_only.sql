-- AQERITH Ideas 14–15: make browser read-only grants explicit.
-- The API uses its server-side PostgreSQL connection for writes. Browser roles must not
-- inherit stale/default DML privileges on communication and notification tables.
-- This follow-up is intentionally additive and safe to apply after the foundation migration.

revoke all privileges on table
  public.communication_threads,
  public.message_templates,
  public.messages,
  public.message_recipients,
  public.delivery_events,
  public.notification_preferences,
  public.notification_events,
  public.notification_deliveries
from anon, authenticated;

grant select on table
  public.communication_threads,
  public.message_templates,
  public.messages,
  public.message_recipients,
  public.delivery_events,
  public.notification_preferences,
  public.notification_events,
  public.notification_deliveries
to authenticated;
