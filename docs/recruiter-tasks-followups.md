# Recruiter tasks and candidate follow-ups

This capability extends Idea 01's "Today's priorities" section without adding a team-workload dashboard or a separate talent-intelligence summary.

## Data model

Migration order for a clean database:
1. `017_recruiter_tasks.sql` creates the organisation-scoped task table and initial RLS policies.
2. `018_recruiter_tasks_policy_hardening.sql` qualifies tenant references in insert/update policies.
3. `019_recruiter_tasks_indexes.sql` adds indexes for task foreign keys and wraps the auth UID call for RLS performance.
4. `020_recruiter_tasks_grant_hardening.sql`, `021_recruiter_tasks_minimum_grants.sql`, and `023_recruiter_tasks_column_grants.sql` remove default elevated grants and allow only approved row operations and columns for `authenticated` (no `anon` privileges).
5. `022_recruiter_task_candidate_delete.sql` cascades candidate deletion to linked follow-up tasks so the required-candidate invariant cannot block candidate deletion.

The table supports recruiter tasks and candidate follow-ups, open/completed/cancelled status, low/normal/high/urgent priority, due timestamps, optional candidate/vacancy links, optional assignee, and completion audit fields. Candidate follow-ups require a candidate. Linked records and assignees are validated against the same organisation.

## API

- `GET /api/tasks?organization_id=...&status=open&limit=50`
- Optional list filters: `status=all|completed|cancelled`, `task_type=task|candidate_follow_up`, `due_before=<ISO timestamp>`
- `POST /api/tasks` creates a task.
- `PATCH /api/tasks/{task_id}` updates task fields or marks a task completed/cancelled/open.

Every endpoint requires authentication and organization membership. The dashboard shows due/overdue open tasks in Today's priorities and offers a task creation/completion panel.

## Verification record

- Applied migrations 017–019 to ATS-Staging only; confirmed `public.recruiter_tasks` exists with RLS enabled, policies are tenant-qualified, task indexes exist, and grants are limited to authenticated row operations with column-level insert/update permissions (no anonymous grants).
- Automated backend tests passed on commit `b1f47660b777433f61dceb5fcb0ad33db4a226dc`; frontend typecheck also passed on that commit. Production build was still running at the time of this note.
- PR #58 is a draft targeting `feat/idea-01-dashboard-command-centre`; it must remain unmerged until CI is green and authenticated staging acceptance succeeds.
- No production database or deployment has been changed by this feature work.

## Known acceptance limits

- Candidate follow-up creation currently selects a candidate from the organisation's candidate list.
- Browser-level create/complete/refresh flows have not yet been verified against a deployment containing this branch.
- The Vercel deployment quota previously blocked new preview builds. Do not claim the new task panel is live until a branch preview is deployed and tested.
