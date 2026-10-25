# AQERITH Recruiter Tasks and Follow-ups

## Purpose

Provide a real, organisation-scoped source for overdue recruiter work and candidate/vacancy follow-ups displayed in Dashboard > Today's priorities. This complements Idea 01 without replacing the existing dashboard sections.

## Data model

Uses the existing `public.recruiter_tasks` table already present in ATS-Staging (migrations 017–023). This PR does not add or apply a duplicate table migration.

- `organization_id`: owning tenant; required.
- `title` and optional `description`.
- `task_type`: task, candidate_follow_up.
- `status`: open, completed, cancelled.
- `priority`: low, normal, high, urgent.
- `due_at`, optional candidate/vacancy links, optional assignee, creator, completion timestamp and audit timestamps.
- The existing staging schema has candidate/vacancy foreign keys; the API additionally verifies linked records belong to the requested organisation.
- RLS is enabled. Policies require organisation membership and restrict assignees to members of the same organisation.

## API

All endpoints require a valid bearer token and organisation membership.

- `GET /api/tasks?organization_id=<uuid>` — list up to 200 tasks; optional status and due_before filters.
- `POST /api/tasks` — create a task.
- `PATCH /api/tasks/<task_id>` — update fields or complete/reopen a task.
- `DELETE /api/tasks/<task_id>` — delete a task.

The API validates candidate, vacancy and assignee organisation membership. Dashboard priorities include open/in-progress tasks due before the next three days; tasks without a due date remain visible in the task workspace but are not surfaced as urgent dashboard priorities.

## Release checklist

- [x] Confirm and reuse the existing recruiter task table and RLS/grant hardening in ATS-Staging.
- [x] Add authenticated CRUD API and tenant checks.
- [x] Add dashboard due-task priority integration.
- [x] Add task workspace and dashboard quick action.
- [x] Add unit tests for task schema validation, membership rejection and dashboard priority mapping.
- [ ] Verify repository migration history is reconciled with the staging migrations 017–023.
- [ ] Review existing tenant-guard triggers/policies and verify the API against staging schema.
- [ ] Verify live create/list/complete/reopen flows in staging.
- [ ] Verify cross-tenant access is denied at API and RLS layers.
- [ ] Confirm the frontend and staging API deployments use the matching branch commit.
- [ ] Obtain user acceptance before merging; production remains untouched.
