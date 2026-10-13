# Staging baseline recovery — current checkpoint

This branch repairs the migration history and establishes a non-production staging schema. Do not merge until a clean replay and acceptance checks pass.

## Changes in this branch
- Added the missing 002_security_performance_hardening.sql and 003_clients_dashboard_indexes.sql files based on the live production catalog.
- Added 007_placements.sql before workflow audit triggers, and 014_team_invitations.sql with the live invitation schema, indexes, and authenticated member/admin policies.
- Removed the duplicate 010_team_invitations.sql and the duplicate timestamped candidate-document definition; retained 013_candidate_documents.sql as the canonical checked-in definition.
- Aligned candidate-document constraints/indexes with production: document type includes certificate, uploaded_by matches production as an unreferenced nullable UUID, SHA-256 format check and live SHA index included. Production and staging both have RLS enabled with no direct candidate-document policies; keep access through the server-side API with explicit tenant checks.
- Restricted direct execution of trigger functions and role helper RPCs; retained authenticated execution of is_org_member(uuid) because tenant RLS policies call it.
- Added 015_restrict_security_definer_execution.sql to harden privileges at the end of the chain.
- Fixed a malformed dollar-quote in the candidate-tags trigger migration on the candidate-tags branch.

## Staging state
- Project: ATS-Staging (riauyrhfnlsxmtgipuxi), region eu-west-1, Postgres 17.
- The 15 baseline public ATS tables were created; candidate-tags migration was then applied, resulting in 17 public application tables.
- All 17 public application tables currently have RLS enabled.
- Candidate tags and assignments each have one authenticated SELECT policy. The assignment tenant-guard trigger exists and its SECURITY DEFINER function is not directly executable by anon/authenticated.
- Catalog checks show audit_workflow_status_change() and capture_record_change() cannot be executed directly by anon/authenticated; current_user_org_role(uuid) and is_org_admin(uuid) are also not directly executable. is_org_member(uuid) is executable by authenticated only, as required by policies.
- Staging contains no application rows.
- Staging advisors still report: no direct policies on candidate documents (intentional only if server-side API access is correctly enforced), the vector extension in the public schema, and an authenticated-callable SECURITY DEFINER warning for is_org_member(uuid). These findings require review; do not label the project security-clean.

## Remaining validation before merge
1. Replay the lexically ordered migration files into a fresh disposable database to confirm clean bootstrap order. Staging was applied through connector migrations in an order that was not strictly lexical, so this is not yet a clean-room replay proof.
2. Compare columns, defaults, constraints, indexes, policies, grants, triggers, storage bucket settings and functions against production catalog. Initial catalog comparison found and corrected the candidate-document uploader FK mismatch, two constraint-name mismatches, and two missing duplicate status indexes; authenticated policy roles intentionally differ from production to close anonymous access.
3. Exercise the candidate assignment trigger with valid and cross-tenant fixtures, then run authenticated API integration tests for member isolation and admin-only create/delete.
4. Run backend/frontend CI on the final candidate-tags commit and record the exact SHA and status.
5. Investigate whether the vector extension can be moved safely and document the intended authenticated execution of is_org_member(uuid).
6. Re-run security/performance advisors after the remaining changes.

## Safety
No production DDL/DML was executed. No production rows were copied. PRs #26, #27 and #29 remain unmerged. Staging is non-production and currently has no application rows.