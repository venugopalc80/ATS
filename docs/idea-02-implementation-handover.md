# AQERITH Idea 02 — Jobs & Requisitions Handover

## Current state
- Feature branch: `feat/idea-02-jobs-requisitions`
- Draft PR: https://github.com/venugopalc80/ATS/pull/59
- PR base: `feat/recruiter-tasks-followups` (Idea 01 work is not merged to main)
- Production database and production deployment: untouched
- Migrations `024_job_requisitions.sql` and `025_job_requisition_fk_indexes.sql`: applied to ATS-Staging only; production untouched
- Current approval model: organisation owner/admin approval; configurable multi-step approvals are out of scope for this slice
- Job conversion creates a draft operational job; recruiters must open/publish it separately

## Implemented in this slice
- Separate organisation-scoped `job_requisitions` table with controlled status, salary/budget/headcount validation, approver metadata, and a unique optional job link
- Authenticated API endpoints for list, create draft, update draft/rejected request, submit, approve, reject, and convert to job
- Idempotent conversion: repeated conversion requests return the existing linked job
- Requisition activity entries written to `audit_events`; edit events capture old/new values for changed fields
- Jobs & Requisitions page with draft creation/edit-resume, tenant-scoped recruiter and hiring-manager assignment controls, search/status filtering, sortable columns, visible pagination, submit/approve/reject/convert actions
- Vacancy close action uses a soft close instead of deleting the job row, preserving application links
- Server-side status-transition and role checks for job updates; organisation membership checks for assignment links

## Acceptance tracker
- [x] Requisition database migration authored with tenant scope, RLS policies, and indexes
- [x] Draft creation API and input validation
- [x] Submit/approve/reject lifecycle endpoints with server-side role checks
- [x] Approved requisition conversion to a linked draft job, idempotent on retry
- [x] Requisition/job audit events added for key actions
- [x] Vacancy closure preserves existing job/application rows
- [x] Apply migrations to ATS-Staging and verify table columns, RLS, policies, and foreign-key indexes against the live staging schema
- [x] Add draft edit/resume in the UI for draft/rejected requisitions
- [x] Add table sorting and visible pagination controls to the workspace (client-side over the API's 100-row result cap)
- [x] Add organisation-scoped recruiter/hiring-manager selectors backed by eligible member roles; validate role and organisation on the API; record old/new assignment values in audit metadata
- [x] Expand tests for draft edit validation, role restrictions, invalid approval transition, cross-organisation client and assignee checks, eligible assignment roles, idempotent conversion retry, and old/new edit audit metadata
- [ ] Add/verify broader database-backed lifecycle and job status-transition tests
- [x] Backend unit tests pass on code/test commit `cb2c15ed94378ae69cf45c5b1378ea287437a204` (GitHub Actions run 39800730424)
- [ ] Confirm frontend typecheck and production build in run 39800730424 (in progress at last check)
- [ ] Vercel preview checks remain blocked by deployment build-rate limiting
- [ ] Authenticated staging/browser acceptance: verify assignment selectors, role restrictions, cross-organisation denial, mobile layout, empty/loading/error states, application preservation
- [ ] Verify preview deployment; do not deploy production or merge before acceptance passes

## Main implementation files
- `supabase/migrations/024_job_requisitions.sql`
- `backend/app/schemas/requisitions.py`
- `backend/app/services/requisition_service.py`
- `backend/app/routers/requisitions.py`
- `backend/app/routers/jobs.py`
- `backend/app/main.py`
- `backend/tests/test_requisitions.py`
- `frontend/app/requisitions/page.tsx`
- `frontend/app/jobs/page.tsx`

## Staging verification
- `job_requisitions` exists in ATS-Staging with RLS enabled.
- Three tenant-scoped SELECT/INSERT/UPDATE policies are present; insert checks `requested_by = auth.uid()` and tenant-scoped client/recruiter/hiring-manager links.
- Migration 025 adds covering indexes for requisition foreign keys; the performance advisor no longer reports requisition foreign keys as unindexed.
- The security advisor returned no findings specific to `job_requisitions`. It still reports pre-existing findings for `candidate_documents`, the shared `is_org_member` SECURITY DEFINER helper, and leaked-password protection.
- No requisition rows were created as part of schema verification.

## Safety notes
- Keep the PR as draft until all unchecked acceptance items are addressed.
- Do not apply this migration to production.
- Existing API job deletion is retained as a compatibility route but now closes rather than physically deleting a vacancy.
- Review direct database grants and RLS with the staging advisor after migration; backend database access is privileged and therefore must enforce organisation membership and cross-tenant link validation itself.
