# Staging baseline recovery — current checkpoint

This is a repair branch, not a deployable release. Do not merge until a clean database replay and schema/security acceptance checks pass.

## Changes in this branch
- Added `007_placements.sql` so the workflow audit trigger has its required relation.
- Added `010_team_invitations.sql` with invitation schema, indexes, and authenticated member/admin policies.
- Reconciled `013_candidate_documents.sql` to production catalog details: document type set includes `certificate`, uploader FK points to `public.profiles`, SHA-256 format check and live SHA index included.
- Added `docs/staging-baseline-recovery.md`.

## Remaining blocking gaps
- The migration chain still does not contain the recorded production baseline/security hardening/dashboard-index migrations as replayable checked-in files.
- Existing migrations have historical naming/version drift. In particular, `004_global_country_support.sql` drops country checks and `008_workflow_audit_actor.sql` assumes placements already exists.
- Staging remains empty. No schema has been applied yet.
- Candidate-tags migration is not applied and needs a real staging schema and tenant/RLS verification before acceptance.

## Live production findings (catalog/advisors only; no writes)
- All 15 public application tables have RLS enabled.
- Security advisor currently flags SECURITY DEFINER functions callable by anon/authenticated: `audit_workflow_status_change()`, `capture_record_change()`, `is_org_member(uuid)`, and `rls_auto_enable()`.
- Security advisor flags `candidate_documents` as RLS-enabled with no recognized policy in its current analysis, despite catalog policies existing; investigate advisor/policy state before considering this resolved.
- Auth leaked-password protection is disabled in project settings.
- Performance advisor reports 12 unindexed foreign keys, two recruiter-notes RLS init-plan warnings, multiple permissive policies on job distribution and invitations, duplicate indexes on jobs/candidates/applications, and unused indexes. Do not delete indexes solely from low-traffic advisor results without workload review.

## Required next checks
1. Reconstruct/review the missing initial security hardening and dashboard index migration history against production catalog.
2. Build a clean, ordered bootstrap or restore exact historical migrations, including auth/storage dependencies.
3. Apply only to the empty staging project.
4. Compare table/column/constraint/index/trigger/function/grant/policy/bucket metadata against the intended schema.
5. Re-run advisors; validate anon denial, authenticated member isolation, audit triggers, invitation role restrictions, and candidate-tag composite tenant guard.
6. Run backend/frontend tests tied to exact commits and record their results. No claim of real DB/API verification until executed.

## Safety
No production DDL/DML was executed. No production rows were copied. Do not merge PR #26, #27, or #29 as part of this work.
