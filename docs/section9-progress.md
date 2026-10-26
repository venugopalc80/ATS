# Section 9 progress — 2026-10-26

Progress percentages are engineering estimates of completed feature scope, not automated coverage or elapsed time.

## Current estimate

- **Section 9 overall:** approximately **46% complete / 54% pending**.
- **Idea 46 — Subscription Plans, Billing & Entitlements:** approximately **50% complete / 50% pending**.
- **Idea 47 — Organisation Settings & Customisation:** approximately **60% complete / 40% pending**.
- **Idea 48 — Help Centre, Onboarding & Product Guidance:** approximately **60% complete / 40% pending**.
- **Idea 49 — Platform Administration, Support & Product Health:** approximately **45% complete / 55% pending**.

## Implemented on feat/section9-commercial-operations

### Idea 46 — Billing
- Schema for plan catalogue, entitlement definitions, organisation subscriptions, provider webhook ledger, usage periods and subscription lifecycle history.
- Billing APIs for plan listing, owner/admin subscription read and server-configured Stripe Checkout creation.
- Checkout retry idempotency: the billing page reuses a per-organisation/plan attempt UUID across reloads and transient failures, and the backend passes a stable derived key to Stripe; cancelled checkout attempts clear stored keys so a new attempt can be created.
- Stripe webhook signature verification, idempotent event receipts, subscription state writes and append-only lifecycle history.
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
- Customer support and restricted platform operations UIs.
- Platform operators can open a case only with an active organisation-approved grant, view the approved conversation, send customer-visible replies, or add internal notes.
- Validation tests authored for support request payloads.

## Staging validation

- Applied billing, subscription history, organisation settings, help/onboarding, platform support and support-grant-scope migrations to ATS-Staging (project ref riauyrhfnlsxmtgipuxi) only.
- Verified the newly added tables have RLS enabled and policies in place for their intended browser roles.
- Seeded four initial help articles in staging; fixed their line breaks in staging and in the migration source.
- No production database changes, merges or production deployments were performed.
- GitHub Actions Section 9 billing/unit-test workflow and Dashboard Update 1 Acceptance workflow both passed on commit e7b6bb20575843a6891a958dc6fff5f023409b84, including Section 9 backend tests, Stripe webhook safeguards, backend acceptance tests, frontend typecheck and production build. Checkout idempotency has since been added with a targeted backend test; fresh CI for those newest commits is pending. End-to-end Stripe checkout/webhook tests remain pending.
- Vercel preview deployments reported the account's daily deployment limit has been reached; preview deployment validation is blocked until the limit resets or the account limit changes.
- Existing unrelated Supabase security advisor findings remain on assessment tables, the public-schema vector extension, a callable SECURITY DEFINER membership helper, and disabled leaked-password protection.

## Main remaining work

- Seed and approve commercial plan/pricing decisions; configure Stripe test secrets and plan price IDs.
- Added stale Stripe subscription event protection using provider event timestamps; equal-second event ordering and provider reconciliation still need further hardening. Checkout retries now use Stripe idempotency keys. Payment-failure/cancellation edge cases remain pending.
- Wire entitlement enforcement into real job, candidate, seat and AI operations; add race-safe quota enforcement.
- Finish subscription and usage UI, settings/help/support UX and role-based access acceptance checks.
- Add integration tests for tenant isolation, access grant expiry/revocation, webhook idempotency and settings version concurrency.
- Re-run backend tests, frontend typecheck/build after the latest UI changes, and staging smoke tests. The Section 9 workflow now includes frontend typecheck/build steps and triggers on platform operations UI changes. Keep PR in draft until checks pass.
- Provision platform operators through a separate privileged process; customer organisation roles must never grant platform access.

## Safety

Production remains untouched. Do not merge or deploy until the acceptance checklist is green and explicitly reviewed.
