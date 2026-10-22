# AQERITH Idea 10 — Interview Kits & Structured Scorecards

## Scope
This branch adds a first implementation increment for versioned interview kits, independent interviewer scorecards, evidence-based review, and human decision records.

## Branch and dependency
- Feature branch: feat/idea-10-interview-kits-scorecards
- Base branch: feat/interview-scheduling-safety (Idea 09 dependency; keep this PR stacked until Idea 09 is integrated)
- Production domain: https://aqerith.com
- Production was not changed.

## Implemented in this branch
- Additive timestamped Supabase migration for interview kits, immutable scorecard templates, competencies, questions, feedback, criterion responses, and evidence-linked review decisions.
- Organisation-scoped RLS policies and revocation of direct browser table grants.
- Published template and submitted assessment immutability enforced by database triggers.
- Admin-only kit creation/version publishing and human review decision recording.
- Interviewer feedback tied to an assigned interviewer, interview, application and exact published template version.
- Draft feedback editable only by its author; submitted feedback is locked.
- Other interviewers' draft feedback is excluded from review responses. Assigned interviewers must submit their own feedback before seeing submitted peer feedback.
- Review shows missing assigned assessments and criterion-level evidence. It does not calculate an automatic hiring verdict.
- Final review decisions require all assigned interviewers to submit, a meaningful rationale, and evidence response IDs. An immutable evidence snapshot and audit event are recorded.
- Frontend kit builder, version publishing, scorecard submission and review surfaces.
- Schema validation tests for scorecard payloads.

## Important review points / known gaps
- The migration has not been applied to ATS-Staging or production. Review its compatibility with the live staging schema and migration history first.
- No local checkout was available through the connected workflow in this session, so backend tests, frontend typecheck/build and migration execution have not yet been run locally.
- CI and authenticated browser acceptance must be verified against the final branch head before merge.
- Verify whether profile IDs are identical to authenticated user IDs in the target Supabase schema, as expected by existing API conventions.
- Confirm jobs, applications, and interviews legacy schema details and foreign-key/delete behaviour against ATS-Staging before applying the migration.
- This increment stores a decision in a dedicated audit-friendly table. It does not itself transition the application pipeline; that integration should be reviewed against the authorised application-stage transition API before being added.
- Admins can review early; assigned interviewers cannot view submitted peer assessments until their own assessment is submitted. Confirm this policy with product stakeholders.
- The current kit builder creates role-specific or general kits and new versions, but does not yet provide a full edit-in-place preview of previously published question sets.
- Missing assessments are displayed as interviewer IDs; a follow-up usability pass should resolve these to names without exposing unnecessary personal data.

## Required acceptance checks
- [ ] Migration applies cleanly to a disposable/staging database and can be rolled back/recovered safely.
- [ ] Tenant A cannot access Tenant B's kits, templates, feedback, responses or decisions.
- [ ] Non-admins cannot create/publish kits or record formal review decisions.
- [ ] Only assigned interviewers can draft/submit scorecards.
- [ ] Drafts are private; submitted feedback is immutable.
- [ ] Submissions require every competency and non-empty evidence.
- [ ] Template versions remain interpretable after a new version is published.
- [ ] Missing feedback is visible and final decisions are blocked until all assigned assessors submit.
- [ ] Decision evidence snapshots and audit events identify the reviewer and supporting evidence.
- [ ] Backend tests, frontend typecheck/build, and authenticated browser checks pass on the latest commit.
- [ ] No merge or production deployment until all required checks pass.

## Files added/changed
- supabase/migrations/20261022120000_interview_kits_scorecards.sql
- backend/app/schemas/interview_scorecards.py
- backend/app/schemas/interview_scorecard_decisions.py
- backend/app/schemas/interview_scorecard_decisions.py
- backend/app/services/interview_scorecard_service.py
- backend/app/routers/interview_scorecards.py
- backend/app/main.py
- backend/tests/test_interview_scorecard_schemas.py
- frontend/app/interview-kits/page.tsx
- frontend/app/interviews/page.tsx
- frontend/app/interviews/[id]/page.tsx
- frontend/app/interviews/[id]/scorecard/page.tsx
