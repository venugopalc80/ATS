# AQERITH Idea 02 — ATS-Staging Acceptance Checklist

## Safety gate

- [ ] Obtain explicit user approval before applying migration 026 to ATS-Staging.
- [ ] Confirm the target is the ATS-Staging project `riauyrhfnlsxmtgipuxi`, region `eu-west-1`.
- [ ] Confirm production project/database identifiers are not being used.
- [ ] Confirm a current staging backup/restore point and the migration rollback/recovery approach.
- [ ] Keep PR #59 as draft; do not merge or deploy production as part of this acceptance.

## Pre-migration baseline (read-only)

- [x] Confirm migrations 024 and 025 are present in ATS-Staging migration history.
- [x] Confirm migration 026 is absent from ATS-Staging migration history.
- [x] Confirm `public.job_requisitions` exists and RLS is enabled.
- [x] Capture current requisition policies and authenticated column-level grants.
- [ ] Recheck the above immediately before any approved migration operation.

## Migration 026 review

- [x] Migration 026 reviewed: insert policy limits creators to owner/admin/hiring_manager/recruiter.
- [x] Migration 026 reviewed: hiring-manager and recruiter assignments require eligible roles in the same organisation.
- [x] Migration 026 reviewed: requester updates are restricted to their own draft/rejected requisitions; owner/admin retains administrative update access.
- [x] Migration 026 reviewed: update policy checks tenant-scoped client and assignee links.
- [x] Disposable PostgreSQL test applies migrations 024, 025 and 026 in order.
- [x] Disposable RLS assertions cover recruiter/hiring-manager creation, viewer denial, invalid assignments, cross-tenant references, requester ownership/status boundaries, admin update access, and protected lifecycle-column grants.
- [x] Expanded update assertions cover cross-organisation client assignment, ineligible hiring-manager/recruiter assignment, and organisation reassignment.
- [x] Full CI run #41329089765 passed: 58 backend tests, frontend typecheck/build, and disposable migration/RLS tests.

## After explicit approval and migration application

- [ ] Apply migration 026 to ATS-Staging only.
- [ ] Verify migration history contains the exact migration 026 entry.
- [ ] Verify the expected INSERT/SELECT/UPDATE policies and policy expressions.
- [ ] Verify authenticated column-level grants still exclude lifecycle/approval fields.
- [ ] Verify no requisition rows or unrelated tables were changed by the migration.
- [ ] Re-run the staging security/performance advisors and compare with the captured baseline.

## Preview smoke checks

- [x] Feature-branch frontend preview for code commit `4a198a20d562b6b9791acfb2ed61d5239ee2ac1a` reached READY: https://aqerith-f667rzdm2-the-pixel-muses.vercel.app
- [x] `/requisitions` returns HTTP 200 and serves the requisitions page bundle; the page correctly remains behind the AQERITH access/session check.
- [x] ATS-Staging API preview health endpoint returns HTTP 200: https://ats-staging-95l0vwjdc-the-pixel-muses.vercel.app/
- [ ] Complete authenticated browser acceptance with authorised staging test accounts. Anonymous HTML/health checks do not prove signed-in workflows or tenant isolation.
- [ ] Verify a fresh preview for the latest branch head after its deployment completes.

## Authenticated API and RLS role matrix

Use test accounts in a dedicated staging organisation and a second organisation. Do not use real candidate or customer data.

- [ ] Owner: create, edit administrative records, approve/reject, and convert approved requisitions.
- [ ] Admin: same administrative permissions as owner.
- [ ] Recruiter: create a requisition, edit/submit own draft or rejected requisition, and convert an approved requisition.
- [ ] Hiring manager: create a requisition and edit/submit own draft or rejected requisition; cannot approve/reject or convert.
- [ ] Viewer: read only; create/update/submit/approve/reject/convert attempts are denied.
- [ ] Recruiter/hiring-manager cannot edit another requester's requisition.
- [ ] Requester cannot edit a submitted/approved/converted requisition.
- [ ] Cross-organisation client and assignee references are rejected on create and update.
- [ ] Ineligible role assignments are rejected on create and update.
- [ ] Direct authenticated writes to status, approval/rejection metadata, requester, tenant, and job-link fields are denied.
- [ ] Organisation A cannot read or mutate Organisation B requisitions.

## UI and workflow acceptance

- [ ] Create and save a draft from the Jobs & Requisitions page.
- [ ] Edit and resume own draft/rejected requisitions.
- [ ] Search, status filter, sort, pagination, and load-more behave correctly.
- [ ] Assignment selectors show only eligible members from the active organisation.
- [ ] Submit, approve, reject (reason required), and convert-to-job workflows behave correctly.
- [ ] Repeated conversion is idempotent and returns the already-linked job.
- [ ] Converted job starts as draft and is not publicly published automatically.
- [ ] Audit events capture create, edit, submit, approve, reject, and conversion actions.
- [ ] Verify mobile layout, keyboard accessibility, empty/loading/error states, and session expiry handling.
- [ ] Confirm closing a job preserves the job row and linked application history.

## Release decision

- [ ] All staging API, RLS, UI, and regression checks pass.
- [ ] Record evidence, test-account roles, timestamps, and any defects.
- [ ] User reviews staging acceptance results and explicitly approves any next release action.
- [ ] Keep production untouched until a separate explicit production approval and release plan.

## Current verified position

- ATS-Staging has migrations 024 and 025 only; migration 026 is not applied.
- Migration 026 has passed isolated disposable PostgreSQL CI tests only.
- PR #59 remains open and draft on `feat/idea-02-jobs-requisitions`, based on `feat/recruiter-tasks-followups`.
- No human review approval is recorded.
- Production database and production deployment remain untouched.
