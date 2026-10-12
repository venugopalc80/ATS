# Dashboard Update 1 — Acceptance Tracking

**Scope:** Recruitment Command Centre dashboard (Idea 01)  
**Status:** Deployed; acceptance is not yet complete.  
**Rule:** Mark an item **PASS** only after its implementation and verification evidence are recorded. A deployment being READY is not acceptance evidence.

## 1. Dashboard navigation and actions

- [ ] **NOT VERIFIED** — “Find matches” opens Match Lab for a selected vacancy. Current dashboard action links to `/jobs`; no Match Lab page was found at the expected `/match-lab`, `/matches`, or `/matching` routes during the initial inspection.
- [ ] **NOT VERIFIED** — KPI cards open the correct filtered records. Current links: open jobs → `/jobs?status=open`; candidates → `/candidates`; interviews → `/interviews`; placements → `/placements`.
- [ ] **NOT VERIFIED** — Pipeline stages and priority items link to the intended filtered records. Pipeline currently links to `/submissions?status=<stage>`; decision priorities link to the general submissions page.
- [ ] **NOT VERIFIED** — Create requisition, Add candidate/import CV, Find matches, and Schedule interview actions work end to end. The requisition quick action currently links to `/jobs` while the header link uses `/jobs?create=1`.

## 2. Metrics and business logic

- [ ] **NOT VERIFIED** — Open jobs, active candidates, interviews today, and active placements reconcile with scoped database records.
- [ ] **REVIEW REQUIRED** — Date-range behaviour is consistent and documented. The dashboard passes dates to the API, but the current KPI queries for open jobs, active candidates, interviews today, and active placements do not use the selected date range; pipeline and recent activity do.
- [ ] **REVIEW REQUIRED** — Priority rules correctly cover today's interviews, missing interview feedback, expiring offers, overdue decisions, and any recruiter tasks that are in scope. Current API code includes interviews, missing feedback, offers expiring within three days, applications awaiting a decision for over three days, and vacancy-health items; no recruiter-task query was identified in the inspected dashboard router.
- [ ] **NOT VERIFIED** — Vacancy-health thresholds are approved, consistently applied, and clearly explained. Current rules flag open vacancies older than 30 days or with fewer than 3 applications.

## 3. Security and activity

- [ ] **NOT VERIFIED** — Automated or repeatable tenant-isolation tests prove users cannot access another organisation's dashboard data.
- [ ] **NOT VERIFIED** — Recent activity displays the correct actor, action, and record destination; actor names currently use `profiles.full_name`.
- [ ] **REVIEW REQUIRED** — All dashboard queries and destination routes enforce the user's organisation membership and record-level permissions. The dashboard endpoint calls `assert_org_member` and filters its queries by `organization_id`; destination routes require separate verification.

## 4. User experience and testing

- [ ] **NOT VERIFIED** — Loading, empty, API-error, and retry states behave correctly in browser testing. UI implementations are present in the current page.
- [ ] **NOT VERIFIED** — Desktop, tablet, and mobile layouts are checked at representative viewport sizes.
- [ ] **NOT VERIFIED** — Automated tests cover dashboard calculations, critical navigation/interaction, and access control. A file at `backend/tests/test_dashboard.py` was not found; inspect the full existing test layout before adding tests.
- [ ] **NOT VERIFIED** — Production smoke tests are run and the results are recorded against the criteria above.

## Initial code-review evidence

- Frontend inspected: `frontend/app/dashboard/page.tsx` at blob SHA `978b31372c53eae8c438ab66f13eba2fef7d4d46`.
- Backend inspected: `backend/app/routers/dashboard.py` at blob SHA `91cf748ed4d027a0a7dc3d627c3886bd128720d4`.
- These are static code-review observations, not proof that browser or production tests passed.

## Completion rule

Close Update 1 only when every in-scope criterion is either verified PASS with evidence or explicitly agreed as out of scope. Do not mark unchecked items as complete based only on deployment status.
