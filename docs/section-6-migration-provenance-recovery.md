# Section 6 — analytics schema provenance recovery

**Review date:** 2026-11-01  
**Repository:** `venugopalc80/ATS`  
**Analytics branch:** `feat/section-6-analytics-bi`  
**Database:** connected Supabase staging project  
**Method:** GitHub pull-request source inspection and read-only PostgreSQL catalogue queries. No staging writes or DDL were performed.

## Executive finding

The Section 6 analytics implementation depends on six existing staging tables whose creation migrations are absent from the Section 6 branch's migration directory:

- `application_stage_history`
- `job_requisitions`
- `recruiter_tasks`
- `recruitment_campaigns`
- `campaign_channels`
- `campaign_memberships`

The source SQL was recovered from earlier, still-unmerged feature pull requests. This narrows the provenance gap: candidate creation and follow-up migrations can be reviewed, but they are not yet part of the main branch's reproducible migration chain. The staging schema is not proof that a clean environment can be built.

## Recovered source migrations and dependencies

| Data dependency | Candidate source | Status at review | Recovered migration files |
|---|---|---|---|
| Recruiter tasks | [PR #58](https://github.com/venugopalc80/ATS/pull/58) | Open, unmerged | `017_recruiter_tasks.sql`, `018_recruiter_tasks_policy_hardening.sql`, `019_recruiter_tasks_indexes.sql`, `020_recruiter_tasks_grant_hardening.sql`, `021_recruiter_tasks_minimum_grants.sql`, `022_recruiter_task_candidate_delete.sql`, `023_recruiter_tasks_column_grants.sql`, `024_recruiter_tasks_tenant_integrity.sql` |
| Job requisitions | [PR #59](https://github.com/venugopalc80/ATS/pull/59) | Open, unmerged | `024_job_requisitions.sql`, `025_job_requisition_fk_indexes.sql`, `026_job_requisition_role_rls.sql`, `027_automatic_job_references.sql`, `028_organisation_job_reference_settings.sql` |
| Application stage history | [PR #69](https://github.com/venugopalc80/ATS/pull/69) | Open, unmerged | `20261026150000_application_stage_history.sql`; follow-up stage configuration `20261101173800_application_stage_config.sql` |
| Recruitment campaigns and channels | [PR #72](https://github.com/venugopalc80/ATS/pull/72) | Draft/open, unmerged | `20261022130000_search_sourcing_features.sql`, `20261022133000_sourcing_link_integrity.sql`, `20261022140000_search_indexes.sql`, `20261022141000_sourcing_browser_grant_hardening.sql`, `20261022142000_campaign_channel_spend_currency.sql`, `20261022143000_talent_pool_processing_basis.sql`, `20261022144000_sourcing_api_only_access.sql` |

These are recovered candidate source files, not confirmation that each file was applied to staging or production. Review the complete migration sequences, including follow-ups, before deciding which SQL becomes canonical.

### Migration ordering collision

PR #58 and PR #59 each introduce a migration with numeric prefix `024`:

- `024_recruiter_tasks_tenant_integrity.sql`
- `024_job_requisitions.sql`

Do not combine these numeric-version files unchanged into one Supabase migration directory. Establish one timestamped, globally ordered migration sequence after checking the actual CLI migration-version parsing and the existing ledger. Preserve the source history in Git and use new forward-only migration identifiers for any reconciliation.

## Read-only staging comparison

The six tables exist in staging and have RLS enabled. The catalogue inspection recovered their columns, constraints, indexes, policies, grants and visible triggers.

### Application stage history

- The staging table has UUID ID, organisation ID, application ID, previous/new stage, actor, reason and timestamp.
- Its application FK references only `applications(id)`; it is not tenant-qualified.
- Its insert policy checks organisation membership and actor identity, but does not verify that the referenced application belongs to the same organisation.
- The recovered PR #69 migration creates an application insert/status-update trigger and a private trigger function to record history. **Those application history triggers were not present in the staging trigger catalogue at this review.**
- No application-stage-history trigger or tenant-qualified FK was added during this review.

**Required follow-up:** validate the application/organisation relationship at database level, and reconcile the missing trigger with the actual deployed application workflow. A suitable forward-only design should add a tenant-qualified FK (with a unique referenced key) after a mismatch preflight, and install/verify the stage-history trigger only after confirming the intended actor/reason propagation and avoiding duplicate history events.

### Recruiter tasks

- Staging has the task columns, status/type/priority checks and organisation-scoped read/insert/update/delete policies.
- Staging has the candidate-only and job-only foreign keys, but the recovered PR #58 follow-up `024_recruiter_tasks_tenant_integrity.sql` adds composite organisation-qualified candidate and job FKs after explicit mismatch preflight.
- Those composite FKs were **not** present in the staging catalogue at review.

**Required follow-up:** reconcile and test the composite tenant FKs before considering task schema provenance complete. Do not apply the preflight migration until the mismatch queries have been run and reviewed.

### Job requisitions

- Staging has the requisition fields, status/headcount/budget/salary checks, unique requisition code and job ID, organisation-scoped read/insert/update policies and supporting indexes.
- The recovered PR #59 migration sequence includes the table creation, additional FK indexes, role-aware RLS and automatic job-reference work.
- The current staging policy snapshot does not establish that the full latest role-aware policy sequence is applied. Compare exact policy definitions and grants, not just policy names.

### Recruitment campaigns and channels

- Staging has campaign, channel and membership tables, currency fields, constraints and indexes.
- The recovered PR #72 source includes campaign attribution, tenant-link validation triggers and an API-only access follow-up.
- A wider read-only trigger inventory now confirms the source migration's tenant-link validation triggers on `talent_pool_memberships`, `recruitment_campaigns`, `referrals`, `campaign_memberships` and `import_row_results`, plus append-only triggers on `talent_pool_membership_events` and `campaign_events`. The source follow-up adds a `candidate_tag_assignments` branch to the shared validation function but does not create a trigger on that table; the staging inventory also has no such trigger. That leaves the intended candidate/tag organisation check inactive for direct database writes unless another constraint or API guard covers it.
- Staging has authenticated SELECT policies on campaign tables, but the grants inventory shows browser roles have no table privileges; only `postgres` and `service_role` have grants. This matches the final API-only access migration's grant intent. The remaining policy definitions still need exact comparison, but the grant state itself is not an outstanding mismatch.

**Confirmed referential-action defect in the recovered and staged campaign schema:** `campaign_memberships` has a composite FK `(organization_id, channel_id)` to `campaign_channels(organization_id, id)` with `ON DELETE SET NULL`. Because `organization_id` is NOT NULL, the default composite SET NULL action attempts to null both columns and can prevent channel deletion. Staging is PostgreSQL 17.11, which supports a column-list referential action; the likely forward-only correction is `ON DELETE SET NULL (channel_id)`. This still needs an isolated-database test for channel deletion, organisation retention and campaign membership integrity before any staging change.

## Current migration ledger

A read-only query of `supabase_migrations.schema_migrations` returned **70 applied versions**, from `20261013110516` through `20261101171326`. The ledger contains identifiers only; it does not preserve the SQL text needed to prove which historical definitions produced the current objects. A targeted name comparison established the following:

- PR #58: migrations `017` through `023` have matching ledger entries; `024_recruiter_tasks_tenant_integrity.sql` does not.
- PR #59: `job_requisitions` and `job_requisition_fk_indexes` have matching ledger entries; role-aware RLS (`026`), automatic job references (`027`) and organisation job-reference settings (`028`) do not.
- PR #69: neither `20261026150000_application_stage_history.sql` nor `20261101173800_application_stage_config.sql` has a matching ledger entry. The latter is newer than the current ledger head.
- PR #72: all seven sourcing/campaign migration concepts have matching ledger entries by migration name: search/sourcing features, sourcing link integrity, search indexes, browser-grant hardening, campaign spend currency, talent-pool processing basis and API-only access. Their source filenames use different timestamps from the staging ledger versions, so the matching name is evidence of an applied migration record, not proof that the source SQL bytes are identical.

The ledger therefore narrows the missing chain to specific follow-ups, but still cannot reconstruct historical SQL. The recovered candidate migrations above are not all represented in the inspected ledger, and a clean database build remains unproven.

Do not insert or edit migration-ledger rows manually. Obtain the authoritative migration history or a reviewed schema dump for every target environment, then reconcile it with the repository.

## Release and implementation sequence

1. Treat PRs #58, #59, #69 and #72 as schema dependencies of Section 6 until their migration content is merged/reconciled into the canonical migration chain.
2. Resolve the duplicate numeric migration prefix and standardise the migration directory on unique timestamped versions.
3. Compare each recovered source migration and follow-up with the staging catalogue, including grants, RLS, constraints, indexes and triggers.
4. Run mismatch preflights for composite tenant constraints in an isolated copy; never silently repair or delete tenant data.
5. Correct and test the campaign channel composite-FK deletion behaviour.
6. Restore/verify application stage-history capture and tenant integrity; reconcile history against authoritative application state.
7. Build a clean isolated database from the proposed canonical migration chain and run backend integration, cross-tenant RLS, saved-report and analytics acceptance tests.
8. Populate only isolated test databases with deterministic synthetic fixtures; do not seed staging with fabricated recruitment records.
9. After approval, apply reviewed forward-only migrations to staging and repeat acceptance checks. Production remains a separate approval gate.

## Safety status

All database inspection in this review was read-only. No staging DDL, DML, grant, policy, trigger, migration-ledger or Storage changes were made. No PR was merged and no production deployment was performed.
