# Section 9 progress — 2026-10-26

Progress percentages are engineering estimates of completed feature scope, not automated coverage or elapsed time.

## Current estimate

- **Section 9 overall:** approximately **47% complete / 53% pending**.
- **Idea 46 — Subscription Plans, Billing & Entitlements:** approximately **53% complete / 47% pending**.
- **Idea 47 — Organisation Settings & Customisation:** approximately **60% complete / 40% pending**.
- **Idea 48 — Help Centre, Onboarding & Product Guidance:** approximately **60% complete / 40% pending**.
- **Idea 49 — Platform Administration, Support & Product Health:** approximately **45% complete / 55% pending**.

## Implemented on feat/section9-commercial-operations

### Idea 46 — Billing
- Schema for plan catalogue, entitlement definitions, organisation subscriptions, provider webhook ledger, usage periods and subscription lifecycle history.
- Billing APIs for plan listing, owner/admin subscription read and server-configured Stripe Checkout creation.
- Checkout retry idempotency: the billing page reuses a per-organisation/plan attempt UUID across reloads and transient failures, and the backend passes a stable derived key to Stripe; cancelled checkout attempts clear stored keys so a new attempt can be created.
- Stripe webhook signature verification, idempotent event receipts, subscription state writes and append-only lifecycle history.
- Subscription provider IDs are checked against the original organisation before stale-event handling; regression coverage verifies a stale event with mismatched tenant metadata is rejected.
- Billing page and unit tests authored for entitlement logic, subscription API states and webhook safeguards.
- Stripe SDK added to backend requirements.

### Idea 47 — Organisation settings
- Versioned settings table with member-read RLS and browser write restrictions.
- Validated backend GET/PATCH API; settings updates are owner/admin-only, versioned and audited.
- Settings UI for brand name, country, currency, timezone, date format and default job preferences.
- Validation tests authored.

### Idea 48 — Help and onboarding
- Per-user, per-organisation onboarding progress table with owner-only RLS visibility.
- API for resuming and updating onboarding checklist progress.
- Versioned searchable help article table and authenticated search endpoint, with initial articles seeded in staging.
- Help centre and getting-started checklist UIs.
- Onboarding payload validation tests authored.

### Idea 49 — Platform operations and support
- Support cases, customer-visible support messages, separately provisioned platform operator roles and scoped support access grants.
- Support access is bound to a specific case, requires organisation admin approval, expires within a maximum of 60 minutes, can be revoked, and is audit-logged.
- Platform support queue and health endpoint avoid exposing candidate records by default.
- The unapproved support queue omits customer-written case subjects; regression coverage verifies subject data is absent before access approval.
- Basic case metadata and customer-written case content use separate scopes. The case-detail endpoint requires explicit `case_content` approval; `case_metadata` alone cannot reveal subject/description. The scope allowlist was expanded on staging and verified in PostgreSQL.
- Customer support and restricted platform operations UIs.
- Regression coverage verifies platform operators cannot read case details without an active organisation-approved access grant, expired requests cannot be approved, and message reads are blocked when no active, unrevoked, unexpired grant matches.
- Platform operators can open a case only with an active organisation-approved grant, view the approved conversation, send customer-visible replies, or add internal notes.
- Validation tests authored for support request payloads.

## Staging validation

- Applied billing, subscription history, organisation settings, help/onboarding, platform support, support-grant-scope, Stripe event-ordering and support-content-scope migrations to ATS-Staging (project ref riauyrhfnlsxmtgipuxi) only. Verified `organization_subscriptions.provider_event_created_at` exists as a nullable `bigint`, confirmed the support grant scope constraint explicitly permits `case_content`, and checked there are no active metadata-only grants that would lose access after this tightening.
- Verified the newly added tables have RLS enabled and policies in place for their intended browser roles.
- Seeded four initial help articles in staging; fixed their line breaks in staging and in the migration source.
- No production database changes, merges or production deployments were performed.
- GitHub Actions Section 9 billing/unit-test workflow (run 55) and Dashboard Update 1 Acceptance workflow (run 746) passed on commit c2524abcd47e709a6e74d12e817dc0d799c18686. This includes backend tests, Stripe webhook safeguards, support queue privacy and access-grant regression tests, frontend typecheck and production build. End-to-end Stripe checkout/webhook tests remain pending.
- Vercel preview deployments reported the account's daily deployment limit has been reached; preview deployment validation is blocked until the limit resets or the account limit changes.
- Existing unrelated Supabase security advisor findings remain on assessment tables, the public-schema vector extension, a callable SECURITY DEFINER membership helper, and disabled leaked-password protection.

## Main remaining work

- Seed and approve commercial plan/pricing decisions; configure Stripe test secrets and plan price IDs.
- Added stale Stripe subscription event protection using provider event timestamps and tenant-binding validation before stale-event handling; equal-second event ordering and provider reconciliation still need further hardening. Checkout retries now use Stripe idempotency keys. Payment-failure/cancellation edge cases remain pending.
- Wire entitlement enforcement into real job, candidate, seat and AI operations; add race-safe quota enforcement.
- Finish subscription and usage UI, settings/help/support UX and role-based access acceptance checks.
- Add deeper integration tests for access-grant expiry/revocation, webhook duplicate delivery and settings version concurrency. Basic regression coverage now verifies cross-tenant stale webhook rejection, expiry-aware approval, scope separation, and denial of case details/messages without a matching active approved grant.
- Re-run backend tests, frontend typecheck/build after the latest code changes, and staging smoke tests. The Section 9 workflow includes frontend typecheck/build steps and the acceptance workflow has passed; the latest migration filename was aligned to the staging migration version. Keep PR in draft until full release checks pass.
- Provision platform operators through a separate privileged process; customer organisation roles must never grant platform access.

## Safety

Production remains untouched. Do not merge or deploy until the acceptance checklist is green and explicitly reviewed.
