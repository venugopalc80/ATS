# Idea 08 — Recruitment Workflow Automation

## Implemented in this branch

- Added migration `014_recruitment_workflow_automation.sql` for tenant-scoped workflow definitions, immutable published versions, run/action/approval records, idempotency constraints, indexes, and RLS membership policies.
- Added Pydantic workflow-definition validation with a bounded linear step list, supported event/action allowlists, unique step keys, condition operators, and approval requirements for high-impact actions.
- Added condition matching and a side-effect-free preview function.
- Added tenant-membership-protected API routes for listing, creating, reading, updating draft definitions, previewing, publishing versions, disabling workflows, and reading run history.
- Restricted publish/disable operations to organisation owners and admins.
- Added a basic workflow builder and run-history page at `/workflows`.
- Added unit tests for condition evaluation, preview safety, unique keys, bounded steps, approval requirements, and rejection-action prohibition.

## Explicitly not complete yet

- Event producers are not wired into application/interview/offer lifecycle transactions.
- There is no worker/queue consumer executing persisted workflow runs or actions yet.
- No retry/recovery endpoint or execution-time action permission gate has been implemented.
- Approval records have a schema, but there is no approval decision API/UI yet.
- The builder currently edits a single linear action and is not a full drag-and-drop workflow canvas.
- The migration has not been applied to any database. Tests/builds have not been executed in a checkout or CI from this session.

## Required next steps before production

1. Wire domain events through a transactional outbox so event creation cannot be lost between database commit and queue publication.
2. Add a worker that pins each run to an immutable workflow version, creates a run with a stable idempotency key, enforces tenant and action permissions at execution time, and safely resumes failed actions.
3. Implement idempotent action handlers; email/message delivery must use a provider idempotency key or transactional outbox rather than assuming a database unique constraint can prevent duplicate external sends.
4. Add approval decision endpoints and audit events, plus pause/emergency-disable checks in the worker immediately before each side effect.
5. Add tenant-isolation, revoked-permission, replay, concurrent-retry, loop/abuse, migration and integration tests; run backend tests and frontend typecheck/build in CI.
6. Verify migration state in a non-production database and test the end-to-end workflow before considering production rollout.

## Safety boundary

Publishing a workflow currently publishes its definition only. It does not execute events or send messages. No automated AI-score-based rejection action is supported. Do not claim the acceptance criteria are complete until the event dispatcher, worker, execution-time permission checks, retry/recovery, and integration tests are delivered.
