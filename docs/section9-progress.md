# Section 9 progress — 2026-10-31

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
- Duplicate Stripe delivery regression coverage verifies a repeated event is acknowledged without repeating subscription processing.
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
- GitHub Actions billing workflow run **41198692173** passed, including entitlement policy, billing API, settings/onboarding/support validation, Stripe webhook safeguards, frontend typecheck and frontend production build.
- GitHub Actions acceptance workflow run **41198692190** passed both backend tests and frontend checks, including frontend typecheck and production build.
- The duplicate Stripe webhook delivery regression test is included in the successful billing workflow.
- Vercel preview deployment checks remain blocked by the account's deployment rate limit; the reported message requests retry after 24 hours. This is separate from the successful GitHub Actions checks.
- No production database changes, merges or production deployments were performed.
- Existing unrelated Supabase security advisor findings remain on assessment tables, the public-schema vector extension, a callable SECURITY DEFINER membership helper, and disabled leaked-password protection.

## Main remaining work

- Seed and approve commercial plan/pricing decisions; configure Stripe test secrets and plan price IDs.
- Harden Stripe event ordering for events sharing the same provider timestamp second. Provider-state reconciliation is preferable to relying on event IDs or assuming arrival order.
- Add payment-failure, cancellation, renewal and subscription-recovery lifecycle integration tests.
- Wire entitlement enforcement into real job, candidate, seat and AI operations; add race-safe quota enforcement. The current policy helpers are not proof that every protected operation enforces limits.
- Finish subscription and usage UI, settings/help/support UX and role-based access acceptance checks.
- Add deeper integration tests for access-grant expiry/revocation and settings version concurrency. Basic regression coverage verifies cross-tenant stale webhook rejection, expiry-aware approval, scope separation, and denial of case details/messages without a matching active approved grant.
- Run staging smoke tests against realistic organisation roles and billing states.
- Provision platform operators through a separate privileged process; customer organisation roles must never grant platform access.
- Resolve the Vercel preview deployment limit and run preview deployment validation.

## Branch and release status

- Feature branch is 83 commits ahead of `main` and 1 commit behind. The only currently identified base-branch commit adds a Section 8 retention-exception integrity migration; it must be incorporated and revalidated before the PR is considered release-ready.
- PR #81 remains draft and unmerged.
- Production remains untouched. Do not merge or deploy until the acceptance checklist is green and explicitly reviewed.
