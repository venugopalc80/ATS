# AQERITH Recruitment Workflow Gap Audit and Delivery Blueprint

**Status:** Planning baseline — code and schema inspection only. No database changes or live workflow tests were performed.

## Findings from the current repository

This audit is based on the current `main` branch.

- **Candidates:** `frontend/app/candidates/page.tsx` and the candidate API support candidate profiles, skills, CV handling and saved views. The candidate model exposes `skills`, but there is no dedicated organisation-scoped tag model or tag-assignment API in the inspected candidate route/service/schema.
- **Applications / pipeline:** `applications` already exists. `ApplicationService.create_application` verifies that the candidate and job belong to the same organisation; the schema has a unique constraint on `(job_id, candidate_id)`. Application status transitions already exist in the service. The remaining work is to make “add to pipeline” and “submit to job” clear, usable recruiter actions and verify stage history/audit behavior.
- **Interviews:** An interviews page, API, service and migration exist. The page can schedule an interview against an application and change interview status. The page inspected does not expose feedback/scorecard entry even though the database migration has `feedback` and `outcome` fields. Time-zone display, rescheduling semantics and participant handling require verification.
- **Rate cards:** No rate-card page, router, schema, service or migration was found in the inspected app/backend/migration listings. Offers and placements exist, but they are not a substitute for rate-card/commercial-term management.
- **Security and tenancy:** Existing routes use organisation-membership checks and application creation checks candidate/job organisation consistency. New functionality must preserve tenant scoping on every read/write and must not rely on a client-supplied organisation ID alone.
- **Testing:** The inspected backend test directory currently contains document-validation tests only. The new workflows need API/service tests and a cross-tenant regression suite.

## Product decisions

1. A candidate has one master profile per organisation.
2. A candidate can be associated with multiple jobs through separate application records; a unique candidate/job pair prevents duplicate applications.
3. “Add to pipeline” creates or opens the application record and assigns the initial stage. “Submit to job/client” is a distinct action/status transition, not merely a visual label.
4. Tags are reusable within an organisation and many-to-many with candidates. Do not model tags as a comma-separated string or overload `skills`.
5. Rate cards are organisation-scoped commercial records with currency, rate basis, effective dates, status and explicit links to the relevant client/job/placement as appropriate. Contract and permanent-placement pricing may require different rate models.
6. Commercial terms and candidate pay details require role-based access and audit history.
7. Dashboard metrics must derive from persisted records and agreed date semantics, not browser-only state.

## Delivery order

### Phase 0 — Baseline and safety
- [ ] Confirm current main and PR branches; keep PR #26 and #27 unmerged until their independent acceptance/security checks pass.
- [ ] Establish a dedicated non-production database and test organisation before applying migrations or exercising destructive flows.
- [ ] Add repeatable test fixtures for two organisations and users with different membership/roles.
- [ ] Document existing API response contracts and application status transitions.

### Phase 1 — Candidate tags
- [ ] Add `candidate_tags` with `organization_id`, normalized name, optional colour/description, timestamps and unique organisation/name constraint.
- [ ] Add `candidate_tag_assignments` with foreign keys and a unique candidate/tag pair; enforce same-organisation ownership (using a composite-key/FK strategy or equivalent server-side validation).
- [ ] Add migration, indexes, RLS policies and audit coverage.
- [ ] Add authenticated, tenant-scoped CRUD/list/assignment endpoints with input validation.
- [ ] Add tag create/manage, assign/remove, filter and search UI.
- [ ] Test duplicate tags, duplicate assignment, unknown tag, cross-tenant IDs, unauthorised role and deletion behavior.

### Phase 2 — Pipeline and job submission
- [ ] Add an obvious “Add to pipeline” action from the candidate profile and candidate list.
- [ ] Select an open job, set source/recruiter and create the application with duplicate handling.
- [ ] Add “Submit to job/client” as a separate guarded action with any required consent/notice checks and submission metadata.
- [ ] Make stage transitions visible and explain invalid transitions; retain audit/history with actor and timestamp.
- [ ] Add candidate, job and application cross-links and status filters.
- [ ] Test same-organisation enforcement, duplicate candidate/job, closed jobs, invalid transitions, and audit history.

### Phase 3 — Interviews
- [ ] Link every interview to an application, candidate and job in the UI.
- [ ] Add interviewer/participant management, explicit time-zone display, reschedule/cancel flows and feedback/scorecards.
- [ ] Capture outcome and feedback author/time; make missing feedback actionable.
- [ ] Test lifecycle transitions, past/future dates, role permissions and tenant isolation.

### Phase 4 — Rate cards
- [ ] Agree the commercial model for permanent, contract and temporary recruitment before finalising the schema.
- [ ] Implement rate-card records and rate-card versions/effective dates; support currency and hourly/daily/annual or fee/percentage basis as applicable.
- [ ] Link terms to client/job/placement with validation; calculate gross margin only where both charge and cost values exist.
- [ ] Add approval, read/write permissions and audit history.
- [ ] Test currency/rate basis, effective-date overlap, missing values, access control and historical integrity.

### Phase 5 — Dashboard and end-to-end acceptance
- [ ] Update dashboard KPIs only after underlying workflows are persisted and verified.
- [ ] Reconcile dashboard counts with tenant-scoped API/database results and document date-range semantics.
- [ ] Verify quick actions, loading/empty/error states, keyboard access and responsive layouts.
- [ ] Run the full journey: candidate → tag → pipeline/application → client submission → interview/feedback → offer → placement.
- [ ] Run tenant-isolation and permission tests across every new endpoint.
- [ ] Complete production smoke tests only after staging acceptance and security checks pass.

## Acceptance gate

Do not mark a phase complete because its page renders or its deployment is READY. A phase is complete only when its migration is reviewed, API and UI persist real records, tenant/role tests pass, error states are covered, and the workflow is demonstrated in the non-production environment.

Do not merge PR #26 or PR #27 until their previously documented independent verification requirements pass.
