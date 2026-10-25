# AQERITH Recruiter Tasks and Follow-ups

## Purpose

Provide a real, organisation-scoped source for overdue recruiter work and candidate/vacancy follow-ups displayed in Dashboard > Today's priorities. This complements Idea 01 without replacing the existing dashboard sections.

## Data model

Migration: `supabase/migrations/014_recruiter_tasks.sql`

- `organization_id`: owning tenant; required.
- `title` and optional `description`.
- `task_type`: general, candidate_follow_up, vacancy_follow_up, interview_follow_up.
- `status`: open, in_progress, completed, cancelled.
- `priority`: low, normal, high, urgent.
- `due_at`, optional candidate/vacancy links, optional assignee, creator, completion timestamp and audit timestamps.
- Candidate/vacancy composite foreign keys prevent linking records across organisations.
- RLS is enabled. Policies require organisation membership and restrict assignees to members of the same organisation.

## API

All endpoints require a valid bearer token and organisation membership.

- `GET /api/tasks?organization_id=<uuid>` — list up to 200 tasks; optional status and due_before filters.
- `POST /api/tasks` — create a task.
- `PATCH /api/tasks/<task_id>` — update fields or complete/reopen a task.
- `DELETE /api/tasks/<task_id>` — delete a task.

The API validates candidate, vacancy and assignee organisation membership. Dashboard priorities include open/in-progress tasks due before the next three days; tasks without a due date remain visible in the task workspace but are not surfaced as urgent dashboard priorities.

## Release checklist

- [x] Add migration file and RLS policies.
- [x] Add authenticated CRUD API and tenant checks.
- [x] Add dashboard due-task priority integration.
- [x] Add task workspace and dashboard quick action.
- [x] Add unit tests for task schema validation, membership rejection and dashboard priority mapping.
- [ ] Review migration against a disposable PostgreSQL database.
- [ ] Apply migration to ATS-Staging only after review and approval.
- [ ] Verify live create/list/complete/reopen flows in staging.
- [ ] Verify cross-tenant access is denied at API and RLS layers.
- [ ] Confirm the frontend and staging API deployments use the matching branch commit.
- [ ] Obtain user acceptance before merging; production remains untouched.
