# Scheduled analytics report delivery — implementation design

**Date:** 2026-11-01  
**Status:** Design prepared; no delivery scheduler, email provider, or staging schema changes enabled.

## Current implementation boundary

The Saved Reports feature stores reusable report definitions. It does not yet send reports on a schedule.

A read-only staging extension check found no installed `pg_cron`, `pg_net`, `http`, or `pgmq` extensions. A repository search found no existing transactional email sender or configuration for Resend, SMTP, or another email provider. The current backend requirements include FastAPI, Supabase, psycopg and Redis, but no dedicated scheduling or email-delivery package.

Scheduled delivery should not be represented as available until both an execution scheduler and a verified sender identity are configured.

## Proposed product behaviour

- Organisation admins create, pause, resume and delete schedules.
- A schedule references one saved report definition and stores frequency, IANA timezone, local delivery time, next due time and status.
- Recipients are selected by organisation-member user IDs, not arbitrary email strings. At delivery time, resolve the current verified email address and confirm the member is still active in that organisation.
- Only aggregate analytics are delivered. Email contains a secure link back to AQERITH; do not attach candidate-level CSV data or expose report data in email previews.
- The destination requires an authenticated session and rechecks organisation membership before showing the report.
- Scheduling is opt-in. The creator sees the report definition, recipients, timezone, frequency and next delivery before activation.

## Proposed persistence model

### `saved_report_schedules`

- `id`, `organization_id`, `report_definition_id`, `created_by`
- `frequency`: daily, weekly or monthly
- `timezone`: validated IANA timezone identifier
- `local_time`: local wall-clock time
- `weekday` and `day_of_month`: nullable frequency-specific values
- `recipient_user_ids`: bounded UUID array, validated against active organisation membership
- `status`: active, paused or disabled
- `next_run_at`, `last_run_at`, `created_at`, `updated_at`

The report definition and schedule must belong to the same organisation. The report creator or an organisation admin may manage a schedule; only admins may schedule a shared report for other members.

### `saved_report_delivery_runs`

- `id`, `organization_id`, `schedule_id`, `scheduled_for`
- `status`: claimed, sent, retryable_failure or permanent_failure
- `attempt_count`, `recipient_count`, `provider_message_id`
- `started_at`, `finished_at`, `sanitised_error_code`

A unique key on `(schedule_id, scheduled_for)` prevents duplicate deliveries. Do not persist message bodies, recipient email snapshots or report result rows in delivery logs.

## Delivery processing and safety

1. A scheduler invokes a private worker endpoint at a fixed short interval.
2. The worker authenticates using a dedicated secret, claims due schedules using row locking and `SKIP LOCKED`, and creates an idempotent delivery-run record.
3. It reloads the saved report and revalidates organisation membership for every recipient.
4. It calculates the next occurrence using the schedule's IANA timezone, including daylight-saving transitions.
5. It sends a minimal email with the report name, scheduled period and authenticated AQERITH link.
6. It records provider message ID and outcome, advances `next_run_at`, and applies bounded exponential retries for transient failures.
7. Permanent failures pause the schedule and notify the schedule owner through the product's normal notification channel.
8. Retain delivery-run metadata for a bounded period (proposed 90 days), then purge it according to the organisation's retention policy.

The worker must never accept an organisation ID, report ID, recipient list or SQL query from an unauthenticated public request without resolving and authorising the persisted schedule.

## Infrastructure decisions required before implementation

1. **Email provider:** no transactional provider is configured in the repository. Recommended direction is a dedicated transactional provider such as Resend, with a verified AQERITH sender domain and an API key stored only in deployment secrets. Google Workspace user mailboxes should not be used as an unattended bulk-delivery service.
2. **Scheduler:** choose and configure one production scheduler. Supabase Cron plus a private Edge Function/HTTP invocation is a viable option, but staging currently has no `pg_cron` or `pg_net` extension installed. A Vercel Cron endpoint is another option if the target project's plan and runtime support it.
3. **Sender identity:** verify a dedicated address such as `reports@aqerith.com` with the chosen provider before enabling delivery.
4. **Schema provenance:** reconcile the existing migration history and validate schedule/run migrations in an isolated database before applying anything to staging.

## Acceptance gates

- Cross-tenant schedule creation, update, read and delete tests.
- Non-member and removed-member recipient tests.
- Admin-only shared-report scheduling tests.
- Duplicate invocation and concurrent worker idempotency tests.
- Daylight-saving and month-end recurrence tests.
- Retry, permanent failure, pause and retention tests.
- No candidate-level data in outbound email or logs.
- Provider webhook signature verification and replay protection, if delivery events are consumed.
- End-to-end staging delivery to a controlled test mailbox before enabling customer schedules.

## Current decision

Do not create active schedules, enable cron, send real email, or apply schedule-related DDL yet. First confirm the email provider and scheduler, then implement the schema and worker as a single reviewed workflow with staging tests.
