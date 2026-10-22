# Section 5 — Employer, agency and client operations: implementation audit

Date: 2026-10-22
Repository: `venugopalc80/ATS`
Base: `main` at `a4960fc290c9759792667363649966f60ff79994`
Working branch: `feat/section-5-org-workspaces-and-client-ops`

## Evidence reviewed

- `README.md`: Next.js/TypeScript frontend, FastAPI/Python backend, PostgreSQL via Supabase, Supabase Storage, Redis background jobs.
- `supabase/migrations/001_core.sql` (introduced by commit `e9060fb1237231f657ff28b6ac2d42a59a3bd07a`): organizations, profiles, organization_members, clients, jobs, candidates, applications and audit_events; organization_members roles are constrained to owner, admin, recruiter, hiring_manager and viewer. RLS and an `is_org_member` helper are present in the initial schema.
- `backend/app/auth.py`: token authentication and organization membership checks; current authorization helpers distinguish organization membership and owner/admin only.
- `backend/app/routers/me.py`: current-user organization listing and organization creation; organization creation adds the creator as owner.
- `backend/app/routers/jobs.py`, `candidates.py`, `applications.py`, `clients.py`: existing organisation membership guards on many routes, often with a read-before-write pattern. This does not yet establish a complete resource/action permission matrix or hiring-manager job-level scope.
- `backend/app/routers/notes.py`: recruiter notes are stored separately from candidates and scoped by organization; the inspected endpoints are candidate-linked and currently membership-gated.
- `backend/app/routers/audit.py`: application audit history is available to organisation members; administrative and role-change events need explicit coverage.
- `backend/app/main.py`: registers jobs, candidates, applications, clients, notes, audit, job distribution, public jobs and document routers.
- `frontend/app/clients/page.tsx`: client CRUD workspace exists and uses the active organisation helper.
- `frontend/lib/organization.ts` is referenced by existing UI code and should be reused for active-organisation resolution.
- Recent open draft PRs include Section 4 (#72), Ideas 09–13 (#71), Idea 04 stage history (#69), and Ideas 14–15 (#68). These are not merged into `main`; implementation must not assume their features are present in the base branch.
- Recent repository commits include tenant-scoping tests and active-organisation resolution fixes. They indicate existing tenant safeguards that must be preserved and tested, not replaced with a parallel implementation.

## Current state by idea

| Idea | Evidence-based state | Main gap to verify/implement |
|---|---|---|
| 22 Multi-tenant organisations/workspaces | Core organisation and membership tables and membership guards exist | Complete endpoint/job coverage, invitation lifecycle, workspace-specific configuration, composite tenant-consistent foreign keys and adversarial tests |
| 23 Roles/permissions/approval policies | Five coarse membership roles and owner/admin checks exist | Central action/resource policy, least privilege, job-level visibility, expanded role model, audited role/approval changes and session revocation policy |
| 24 Agency client portal | Client records and client workspace exist | Explicit agency-client relationship, candidate/job/client-scoped submission grants, client-safe APIs, revocation and audit trail |
| 25 Hiring team collaboration/internal notes | Candidate recruiter notes and audit events exist | Threaded comments, mentions, attachment inheritance, confidential note controls and clear internal-vs-candidate visibility |
| 26 Careers website builder | Public jobs router exists | Verify publication/version model, organisation branding, public field allowlist, verified custom domains, stale-job withdrawal and accessible public forms |
| 27 Job board distribution | Job distribution router and Google indexing service exist | Verify provider abstraction/capability contracts, per-channel publication state, idempotency, credential handling, sync and withdrawal |

## Critical design rules

1. Do not use a client-provided `organization_id` as proof of access. Authenticate the actor, resolve membership, then authorize the requested action against the resource and tenant.
2. Use explicit resource grants for agency/client access. Do not add external client users as agency-wide members or expose the agency's candidate pool.
3. Keep internal recruiter notes, commercial fees, sourcing details and private attachments out of client/public response models by default.
4. Scope every background task to an immutable tenant/resource context and re-check current authorization before consequential work.
5. Prefer tenant-consistent composite foreign keys where related rows carry `organization_id`; add constraints only after checking existing data and migration history.
6. Treat role/session policy changes as security-sensitive and audit actor, target, previous/new value, timestamp and reason where applicable.
7. Do not assume a job-board posting API exists. Ship only providers with a documented, supported integration path.
8. Never apply migrations to production or deploy/merge before acceptance checks pass.

## Implementation sequence

1. Finish the schema/router audit and map all current route methods to actions/resources.
2. Implement central permission definitions and backend enforcement; add job-level assignment/scope rules.
3. Add organisation invitation and membership lifecycle with audit events, and a documented session-revocation policy.
4. Add explicit agency-client relationships and candidate/job/client-specific sharing grants, with revocation.
5. Extend collaboration notes into permission-aware threads/mentions and ensure attachments inherit parent access.
6. Harden the careers publication boundary and verify the existing public jobs API before adding a builder.
7. Review the existing job distribution router and implement only the missing provider abstraction/status/idempotency capabilities.
8. Add migrations, unit/API/database tests, cross-tenant adversarial tests, background-task tests, frontend typecheck/build and authenticated preview acceptance.

## Release acceptance gates

- Changing an identifier cannot expose another tenant's record.
- Every sensitive endpoint checks membership plus the required action/resource permission.
- Hiring managers are restricted to explicitly assigned jobs/applications.
- Role and grant changes cannot be self-escalated and are auditable.
- Cross-tenant sharing is explicit, minimal, revocable and auditable.
- Client/public APIs never expose agency-private notes, fees or draft/internal job fields.
- Background work re-validates tenant and permission context and is idempotent where it can create external side effects.
- Public careers pages contain only published, current jobs and safe fields.
- Job-board credentials never reach the browser; provider retries do not create duplicates where idempotency is supported.
- Migration history is reconciled with the staging schema, and tests plus authenticated preview checks pass.

## Verification limitation

This audit was performed through repository file/commit inspection. No local checkout or configured test/database runtime was available through that inspection path, so no backend suite, frontend typecheck/build, database migration, staging integration test or authenticated browser acceptance is claimed as run.
