# Ideas 14–15: communication and notification foundations

## Included in this branch
- Tenant-scoped communication threads tied to an application and its actual candidate.
- Separate internal notes (`visibility=internal`, `channel=internal`, `status=internal`) and candidate-visible message drafts.
- Versioned message templates with draft/approved/retired lifecycle and admin-only approval.
- Idempotency keys for message draft creation.
- Delivery-event and recipient delivery-status storage.
- Per-user, per-organisation notification preferences for in-app, email and SMS channels.
- Essential account-security and critical-service notification types cannot be disabled through the preference API.
- RLS enabled on all new tenant-owned tables, tenant membership policies, least-privilege table grants, composite tenant foreign keys and an application/candidate consistency trigger.

## Explicitly not enabled yet
- No email or SMS provider is configured by this branch. Candidate messages are saved as drafts and are not sent.
- No provider webhook endpoint is exposed yet. Delivery events must not be accepted from an unauthenticated caller; implement provider signature verification before ingestion.
- No background notification worker, retry scheduler or delivery deduplication worker is included yet. The database has idempotency and delivery state foundations only.
- Notification events and deliveries are system-generated; the authenticated client cannot create them directly.
- Candidate portal identity, account recovery, session revocation and candidate-safe application APIs are not implemented here.

## Verification required before production
1. Apply this additive migration to an isolated staging database after checking migration history.
2. Run backend unit/integration tests and frontend typecheck/build.
3. Test two-tenant isolation, candidate/application mismatch rejection, internal-note non-deliverability, approved-template enforcement and duplicate idempotency keys.
4. Configure an email provider and signed event webhook before enabling outbound messages.
5. Add a retry-safe worker with provider idempotency, opt-out enforcement and essential-notification classification before enabling notification delivery.
6. Run authenticated browser and accessibility checks.

This branch is a foundation increment, not a production-ready outbound messaging release.
