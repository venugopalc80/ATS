# AQERITH Section 9 — Implementation plan and baseline

Branch: `feat/section9-commercial-operations`
Repository: `venugopalc80/ATS`
Target environment for validation: `ATS-Staging` (Supabase project ref `riauyrhfnlsxmtgipuxi`)
Production is read-only for this work.

## Baseline verified

- README describes Next.js 15 + TypeScript, FastAPI + Python, PostgreSQL/Supabase, Redis, and Stripe as the intended stack.
- Frontend package is at `frontend/package.json`; scripts include `build` and `typecheck`.
- Backend FastAPI entry point is `backend/app/main.py`; existing routers include jobs, candidates, applications, organisation context, audit, interviews, offers, placements and documents.
- `backend/app/routers/me.py` exposes the user's organisation memberships and creates organisations. Roles observed in the database are owner, admin, recruiter, hiring_manager and viewer.
- Both staging and production databases contain organisation-scoped recruitment tables and RLS-enabled tables. Staging includes organisations, organisation_members, audit_events, jobs, candidates, applications, organization_invitations, application_stage_history and related recruitment records.
- No matching billing, onboarding or support implementation was found by the initial repository code searches. This is not proof that no implementation exists; targeted source-tree review is still required.
- Stripe appears in the README as intended architecture, but no Stripe implementation has been verified.

## Dependencies to inspect before feature code

1. Auth and tenant access: `backend/app/auth.py`, `backend/app/db.py`, organisation membership and role checks, existing audit event conventions.
2. Database migration layout, migration history, RLS policies, triggers, and organisation-scoped foreign keys.
3. Frontend route/layout conventions, navigation, shared form/table components, API client and error handling.
4. Stripe SDK and webhook configuration, if present; background task and Redis conventions; environment-variable validation.
5. Existing application stage history and organisation data model, to ensure settings changes do not rewrite historical events.
6. Deployment configuration and CI checks. No production deployment or migration is permitted from this branch.

## Implementation sequence

### Phase A — Verify repository and security boundaries
- Map the complete relevant source tree and migration history.
- Confirm the authoritative development/base branch and staging database configuration.
- Document current API, UI, audit, and role patterns.
- Run baseline typecheck/build and available backend tests where execution is available.

### Phase B — Subscription plans, billing and entitlements
- Define plans, versioned entitlement keys/limits, organisation subscriptions, billing event idempotency, usage periods, and plan-change history.
- Keep billing provider identifiers and event payloads on the server; verify Stripe webhook signatures and process events idempotently.
- Enforce limits in backend operations, not just UI. Define explicit behaviour for trials, payment failures, cancellation, upgrades and downgrades.
- Keep billing access separate from candidate/application access.

### Phase C — Organisation settings
- Add typed, validated, versioned organisation settings with safe defaults.
- Gate mutations to owner/admin (or the established equivalent), record audit events, and preserve immutable historical stage/event meaning.
- Add compatibility tests and recovery/default behaviour.

### Phase D — Help centre and onboarding
- Implement resumable per-user onboarding progress with required vs optional steps.
- Provide contextual, versioned guidance and searchable help content; avoid unnecessary behavioural tracking.
- Ensure one user's progress is not broadly visible to other organisation members.

### Phase E — Platform operations and support
- Keep platform operator roles separate from customer organisation roles.
- Implement support cases, service/tenant incident links, health signals and time-limited, purpose-bound exceptional access grants.
- Audit support actions and exports. Avoid candidate content in default operations dashboards.

### Phase F — Verification and handover
- Add unit/integration tests for tenant isolation, authorisation, entitlement enforcement, idempotency, lifecycle transitions, settings validation/versioning, onboarding privacy, and support-access expiry.
- Validate migrations against staging and confirm RLS, grants and database advisors where available.
- Run frontend typecheck/build and backend tests. Record exact results, unresolved failures, commit and PR.
- Do not merge or deploy production until acceptance checks are reviewed and explicitly approved.

## Non-negotiable safeguards

- Never trust frontend billing status or usage counts.
- Never use client-editable profile metadata as an authorisation source.
- Never grant broad candidate-data access to billing administrators or support operators by default.
- Keep tenant identifiers in every organisation-owned query and enforce access in the backend and database.
- Treat webhook payloads as untrusted until signature verification succeeds.
- Do not rewrite past application-stage events when labels/configuration change.
- No production schema changes, production data changes, merges, or deployments as part of exploratory implementation.


## Current implementation status — 2026-10-31

Section 9 implementation is now present on `feat/section9-commercial-operations`:

- **Idea 46:** subscription plan and entitlement schema, billing APIs, Stripe Checkout, webhook signature verification, idempotent receipt handling, subscription history and billing UI are implemented. Backend entitlement policy helpers exist, but they are not yet wired into all protected recruitment operations. Stripe payment-failure/recovery lifecycle handling, automated reconciliation of quarantined equal-second events and end-to-end provider tests remain open. The webhook now refuses equal-second updates and records them as ignored with `ambiguous_provider_event_timestamp`; this prevents arrival order from silently overwriting subscription state.
- **Idea 47:** organisation settings schema, owner/admin API, versioning, audit and settings UI are implemented. Concurrency and role acceptance tests remain open.
- **Idea 48:** resumable onboarding progress, searchable help content, API and initial UI are implemented. Broader content, UX and privacy acceptance remain open.
- **Idea 49:** scoped support cases, customer-approved time-limited access grants, support APIs and operations/support UIs are implemented. Deeper expiry/revocation integration tests and privileged platform-operator provisioning remain open.
- Staging-only migrations and seed content have been applied and checked. Production has not been changed.
- GitHub Actions runs 41198692173 (billing), 41198692190 (acceptance), 41200410637 (billing) and 41200410650 (acceptance) passed. The latest branch-integrated runs 41202107706 (billing) and 41202107713 (acceptance) were started after the equal-timestamp quarantine and branch integration; final results must be checked before release review.

The feature branch includes the Section 8 retention-exception integrity migration and is now 91 commits ahead of `main` with no commits behind. Revalidation against the integrated branch is in progress.

Current estimated feature completion remains 47% overall. These are engineering scope estimates, not test coverage or release readiness. Keep PR #81 in draft; do not merge or deploy without explicit approval.
