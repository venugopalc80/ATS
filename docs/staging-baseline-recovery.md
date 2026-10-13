# Staging baseline recovery

## Status

- Staging project: `riauyrhfnlsxmtgipuxi` (PostgreSQL 17, `eu-west-1`).
- Production project: `olsziyaepfesjtkceuzo` — inspected read-only only.
- No production DDL/DML was executed.
- No migration has been applied to staging as part of this recovery yet.
- PRs #26, #27, and #29 remain open/unmerged.

## Why a normal replay is unsafe

The migration files on `main` do not represent a complete, replayable version of the migration history recorded in production. Production records these migrations:

| Production version | Recorded name |
| --- | --- |
| 20261004123217 | initial_core_schema |
| 20261004143930 | security_performance_hardening |
| 20261004144242 | clients_dashboard_indexes |
| 20261004145536 | global_country_support |
| 20261004171018 | interviews |
| 20261004171311 | 006_offers |
| 20261004173641 | 007_placements |
| 20261005193908 | workflow_audit_actor |
| 20261007155002 | 009_recruiter_notes |
| 20261007165934 | 010_team_invitations |
| 20261009193843 | record_history_and_append_only_notes |
| 20261010094403 | job_distribution_channels |
| 20261012091011 | candidate_documents_bulk_cv_import |

The current repository has ordinally named SQL files such as `001_core.sql`, `004_global_country_support.sql`, `005_interviews.sql`, `006_offers.sql`, `008_workflow_audit_actor.sql`, `009_recruiter_notes.sql`, `010_record_history_and_append_only_notes.sql`, `011_admin_role_helpers.sql`, `012_job_distribution.sql`, and `013_candidate_documents.sql`, plus a timestamped candidate-documents migration. Important schema steps present in production history are absent as files, including the placements and team-invitations migrations. For example, `008_workflow_audit_actor.sql` creates a trigger on `placements`, but a clean replay of the checked-in chain does not create that table first.

## Production catalog facts gathered (schema only)

Production currently has 15 public application tables: `applications`, `audit_events`, `candidate_documents`, `candidates`, `clients`, `interviews`, `job_distribution_channels`, `jobs`, `offers`, `organization_invitations`, `organization_members`, `organizations`, `placements`, `profiles`, and `recruiter_notes`.

- `placements` includes organization/application/job/candidate relations, optional offer/client relations, lifecycle status, start/end dates, fee fields, and creator attribution. Its production constraints enforce valid lifecycle values, end date not before start date, and fee percentage between 0 and 100.
- `organization_invitations` includes organization, email, role, inviter, token hash, expiry, acceptance timestamp, and timestamps. Production has a partial unique index for pending invitations by organization and case-insensitive email, plus token-hash and organization/created-time indexes.
- The production catalog contains security-definer helpers/triggers and tenant RLS policies; staging must be tested for effective role grants and tenant isolation, not merely for table existence.
- The existing candidate-documents migration on `main` differs from the production catalog in details: repository migration allows `portfolio` document type but live constraint allows `certificate`; repository migration uses `uploaded_by` referencing `auth.users`, while live catalog uses `profiles`; live catalog also has a SHA-256 format constraint and a SHA index. This drift must be reconciled explicitly rather than hidden in a staging bootstrap.

## Recovery acceptance gates

1. Create a clean, reviewable staging bootstrap based on catalog metadata and checked-in app expectations; do not copy production rows.
2. Ensure dependency order is explicit: core tables and helpers before workflow/audit triggers; placements before workflow audit trigger; team invitations and their indexes/policies included; candidate documents reconciled to the live contract.
3. Review the bootstrap against the current repository migrations and generated types before applying it.
4. Apply schema only to the dedicated empty staging project.
5. Compare staging tables, columns, constraints, indexes, triggers, functions, grants, RLS policies, and storage bucket configuration against the intended schema.
6. Apply candidate-tags migration only after the baseline passes review, then verify its composite tenant constraint, RLS, trigger privileges, and expected API tests.
7. Keep PRs #26, #27, and #29 unmerged until their respective acceptance gates pass.

## Important limitations

A catalog comparison is not an application integration test. A successful DDL run is not proof of tenant isolation. The candidate-tags migration has not been applied to any project and its API tests have not yet been run against a real database in this recovery.
