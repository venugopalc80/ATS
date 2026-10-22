# AQERITH Idea 02 — Jobs & Requisitions Handover

## Current state
- Feature branch: `feat/idea-02-jobs-requisitions`
- Draft PR: https://github.com/venugopalc80/ATS/pull/59
- PR base: `feat/recruiter-tasks-followups` (Idea 01 work is not merged to main)
- Production database and production deployment: untouched
- Migration `024_job_requisitions.sql`: committed only; not applied to staging or production
- Current approval model: organisation owner/admin approval; configurable multi-step approvals are out of scope for this slice
- Job conversion creates a draft operational job; recruiters must open/publish it separately

## Implemented in this slice
- Separate organisation-scoped `job_requisitions` table with controlled status, salary/budget/headcount validation, approver metadata, and a unique optional job link
- Authenticated API endpoints for list, create draft, update draft/rejected request, submit, approve, reject, and convert to job
- Idempotent conversion: repeated conversion requests return the existing linked job
- Requisition activity entries written to `audit_events`
- Jobs & Requisitions page with draft creation, search/status filtering, submit/approve/reject/convert actions
- Vacancy close action uses a soft close instead of deleting the job row, preserving application links
- Server-side status-transition and role checks for job updates; organisation membership checks for assignment links

## Acceptance tracker
- [x] Requisition database migration authored with tenant scope, RLS policies, and indexes
- [x] Draft creation API and input validation
- [x] Submit/approve/reject lifecycle endpoints with server-side role checks
- [x] Approved requisition conversion to a linked draft job, idempotent on retry
- [x] Requisition/job audit events added for key actions
- [x] Vacancy closure preserves existing job/application rows
- [ ] Apply migration to ATS-Staging and verify RLS/grants/policies against the live staging schema
- [ ] Verify draft edit/resume in the UI (API supports update, current page still needs an edit/resume interaction)
- [ ] Add table sorting and visible pagination controls to the workspace
- [ ] Add a recruiter assignment UI and confirm reassignment history metadata contains old/new values
- [ ] Add endpoint/unit tests for each lifecycle transition, conversion retries, tenant-link mismatch, and job status transitions
- [ ] Run CI on the latest feature commit (the first PR-triggered run tested an earlier head)
- [ ] Authenticated staging browser acceptance: roles, cross-organisation denial, mobile layout, empty/loading/error states, application preservation
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

## Safety notes
- Keep the PR as draft until all unchecked acceptance items are addressed.
- Do not apply this migration to production.
- Existing API job deletion is retained as a compatibility route but now closes rather than physically deleting a vacancy.
- Review direct database grants and RLS with the staging advisor after migration; backend database access is privileged and therefore must enforce organisation membership and cross-tenant link validation itself.
