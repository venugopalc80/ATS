# Section 9 progress — 2026-10-22

## Progress percentages

Percentages are engineering estimates of completed scope, not automated coverage or elapsed time.

- Section 9 (Ideas 46–49): approximately 12% complete / 88% pending.
- Idea 46 — Subscription Plans, Billing & Entitlements: approximately 35% complete / 65% pending.
- Idea 47 — Organisation Settings & Customisation: 0% complete / 100% pending.
- Idea 48 — Help Centre, Onboarding & Product Guidance: 0% complete / 100% pending for the requested full scope. Existing first-workspace onboarding page is baseline functionality, not completion of this idea.
- Idea 49 — Platform Administration, Support & Product Health: 0% complete / 100% pending for the requested full scope.

## Implemented

- Staging schema: plan catalogue, entitlement definitions, organisation subscriptions, webhook event ledger, usage-period counters, and subscription lifecycle history.
- RLS and basic browser-role grants/policies for the new billing tables.
- Billing API endpoints: active plan listing, organisation admin subscription lookup, server-configured Stripe Checkout Session creation.
- Stripe webhook receiver with signature verification, event-id idempotency, subscription lifecycle state writes, tenant metadata checks, and append-only subscription history.
- Unit tests authored for entitlement policy, billing read endpoints, and webhook signature/status safeguards.
- Stripe SDK added to backend requirements.

## Staging validation

- Applied the subscription/entitlement, webhook ledger policy, and subscription history migrations to Supabase project `riauyrhfnlsxmtgipuxi` (ATS-Staging).
- Queried database catalog and confirmed all six new tables have RLS enabled and at least one policy.
- No production database changes or deployment were made.
- Full repository test suite has not been run: this execution environment cannot reach GitHub to clone the repository. Unit tests are committed but their execution remains unverified.
- Supabase security advisors still report pre-existing findings on assessment tables, public-schema vector extension, callable SECURITY DEFINER membership helper, and disabled leaked-password protection.

## Remaining for Idea 46

- Define and seed commercial plans, prices and entitlement limits.
- Configure Stripe secrets and price IDs in the staging deployment.
- Test checkout and signed webhook flows end to end using Stripe test mode.
- Handle provider event ordering/reconciliation, cancellation and payment-failure lifecycle edge cases.
- Wire entitlement checks into actual job, candidate, seat and AI operations.
- Build billing UI and usage presentation.
- Run full tests, API integration tests, tenant-isolation checks, typecheck/build and staging smoke tests.

## Safety

Feature branch: `feat/section9-commercial-operations`.
Production remains untouched. Do not merge or deploy until the full verification checklist is green and explicitly reviewed.
