# Idea 04 — Supabase migration reconciliation note

**Status:** investigation only. No Supabase schema writes, migration repairs, or production deployments were performed during this review.

**Repositories / branch:** `venugopalc80/ATS`, canonical feature branch `feat/idea-04-application-pipeline`.

## Verified environment state

Read-only checks were performed on 31 October 2026.

### ATS-Staging

Project ID: `riauyrhfnlsxmtgipuxi`

- The latest recorded migration is `20261026143744` (`section9_support_content_scope`).
- `public.application_stage_history` already exists.
- Its columns match the Idea 04 history migration: `id`, `organization_id`, `application_id`, `previous_stage`, `new_stage`, `actor_user_id`, `reason`, and `created_at`.
- Its primary key, organisation/application/profile foreign keys, 1,000-character reason constraint, and `(organization_id, application_id, created_at DESC)` index match the intended migration.
- RLS is enabled. The member read and member insert policies exist.
- The two application history triggers exist and call `private.record_application_stage_history()`.
- The existing trigger function body matches the function body in the checked-in history migration. It is owned by `postgres`, is SECURITY DEFINER, and its observed execute ACL is `postgres=X/postgres`.
- The Supabase migration ledger does **not** contain version `20261026150000`.
- `public.application_stage_config` does not exist.
- The applications status check still permits only the legacy values: `new`, `screening`, `submitted`, `interview`, `offer`, `hired`, `rejected`, and `withdrawn`.

### ATS production

Project ID: `olsziyaepfesjtkceuzo`

- The latest recorded migration is `20261012091011` (`candidate_documents_bulk_cv_import`).
- Neither `public.application_stage_history` nor `public.application_stage_config` exists.
- The applications status check still permits only the legacy values listed above.
- Production's migration ledger is materially behind staging's. The Idea 04 migrations must not be applied in isolation until the full production migration/schema gap is reviewed.

## Safe reconciliation plan

1. Keep both Idea 04 migrations in the feature branch. Do not edit a migration that may already have been applied to a live database.
2. Capture a fresh schema-only backup and migration-ledger export for each environment before any staging release activity.
3. Compare the complete live definitions for the staging history table, constraints, indexes, policies, grants, function owner/ACL/body, and triggers against migration `20261026150000_application_stage_history.sql`. The checks performed so far show the expected objects, but the origin of those objects is not yet established.
4. Trace the staging objects to their original migration, deployment, or manual change. Record that provenance and obtain approval from the database owner.
5. If and only if the live staging objects are confirmed equivalent and the approved deployment process accepts that provenance, reconcile the migration ledger using the supported Supabase migration-repair workflow. Do not insert/update rows in `supabase_migrations.schema_migrations` manually and do not rerun the history DDL blindly.
6. Apply `20261026150100_application_stage_config.sql` to staging only in an approved release window, after history migration state is reconciled. Verify seeded stage rows, status constraint, organisation-creation trigger, RLS, and browser-role grants.
7. Run the authenticated recruiter workflow and database-backed tenant-isolation acceptance tests against staging. Preserve existing staging data.
8. Treat production separately. First produce a complete chronological migration and schema reconciliation plan from its recorded version `20261012091011` to the intended release state. Do not assume that applying only the two Idea 04 migrations is safe.
9. Production application requires a separate explicit approval, backup/restore plan, maintenance window, and post-deployment verification.

## Release blockers

- Staging history migration provenance and ledger reconciliation are unresolved.
- Stage configuration has not been applied to either live environment.
- Production has a substantial migration-history gap relative to staging.
- No live database write or production deployment is authorised by this note.

## Evidence boundary

The statements above describe read-only metadata inspection. Automated PostgreSQL smoke tests run in GitHub Actions use a disposable database and do not prove that live Supabase migration history is reconciled or that the production environment is ready.
