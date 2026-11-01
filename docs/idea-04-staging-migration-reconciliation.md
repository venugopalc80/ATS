# Idea 04 — Supabase migration reconciliation note

**Status:** staging investigation updated 1 November 2026. No live schema writes or migration repairs have been executed in this update.

**Repository / branch:** `venugopalc80/ATS`, canonical feature branch `feat/idea-04-application-pipeline`.

## Verified environment state — 1 November 2026

### ATS-Staging

Project ID: `riauyrhfnlsxmtgipuxi` (ACTIVE_HEALTHY, PostgreSQL 17.11).

- The latest recorded migration is now `20261101171326` (`organization_timezone`), not the previously recorded `20261026143744`. This changes the required ordering for any new migration.
- `public.application_stage_history` exists with RLS enabled.
- Its columns, primary key, organisation/application/profile foreign keys, reason-length check, and `(organization_id, application_id, created_at DESC)` index match the intended Idea 04 history migration.
- Both expected RLS policies exist: member read and member insert.
- The two expected application triggers exist and call `private.record_application_stage_history()`.
- The function body matches the checked-in migration, is owned by `postgres`, is SECURITY DEFINER with an empty search path, and its observed execute ACL is `{postgres=X/postgres}`.
- The table ACL is `{postgres=arwdDxtm/postgres,service_role=arwdDxtm/postgres}`; browser roles `anon` and `authenticated` have no table grants.
- The Supabase migration ledger does **not** contain version `20261026150000`.
- `public.application_stage_config` is absent.
- `applications_status_check` still allows only the legacy values: `new`, `screening`, `submitted`, `interview`, `offer`, `hired`, `rejected`, and `withdrawn`.
- Current data counts: 1 organisation, 0 applications, 0 history rows. There are no missing-history, orphan-history, or organisation-mismatch rows. The staging organisation currently has no application data to backfill.

### ATS production

Project ID: `olsziyaepfesjtkceuzo`.

- Its migration ledger remains materially behind staging; the latest recorded migration in the last checked snapshot was `20261012091011`.
- Neither Idea 04 table exists and the application status check is legacy.
- Production has not been changed. It requires a separate chronological schema/migration reconciliation and its own backup and release plan.

## Reconciliation decision

1. The live history objects are structurally equivalent to the checked-in history migration. This is strong equivalence evidence, but it does not establish who originally created them or the exact deployment event. Do not rerun the history DDL merely to make the ledger appear consistent.
2. The supported Supabase procedure for this state is `supabase migration repair --status applied 20261026150000`, after the schema comparison and provenance are accepted. Never insert or update `supabase_migrations.schema_migrations` directly.
3. The connected Supabase tools expose migration listing, SQL execution and migration application, but do not expose the CLI `migration repair` command or a database backup/export operation. Do not emulate repair with direct SQL, and do not claim a schema backup has been taken.
4. The config migration has been moved to `20261101173800_application_stage_config.sql`, after the staging migration head `20261101171326`. The PostgreSQL migration smoke test now points to the new filename. The old out-of-order file `20261026150100_application_stage_config.sql` has been removed from this feature branch. The updated branch must pass its exact-head CI before any staging application.
5. Before any staging write, obtain a schema-only backup and migration-ledger export using the Supabase dashboard/CLI or another authorised backup path. The live staging application and history tables currently contain zero rows, but that does not replace a backup.
6. Then use the approved Supabase CLI workflow from an authenticated environment to repair the history version as applied, apply the newly timestamped config migration to staging, and verify the status constraint, ten default stages for the existing organisation, organisation-creation trigger, function ACL, RLS policies, and browser-role denial.
7. Complete live JWT/authentication and tenant-isolation acceptance. Disposable PostgreSQL CI tests do not prove live Supabase JWT validation or RLS behaviour.

## Current CI evidence

Canonical PR #69 head: `07c6290cd75755d0b89f18c28530edf34eede6f4`.

GitHub Actions run #962 completed successfully on that exact head: 74 backend tests passed, 4 skipped, PostgreSQL 16 migration smoke test passed, frontend typecheck passed, and production build passed. This is code/CI evidence only, not live staging acceptance.

## Release blockers

- The origin/provenance of the already-present history objects is not yet established.
- The supported CLI migration-repair operation and a schema-only backup/export path are not available through the connected tools in this session.
- The config migration timestamp is older than the current staging migration head and must be corrected before application.
- Stage configuration has not been applied.
- Live Supabase JWT/RLS, authenticated recruiter workflow, and tenant-boundary acceptance remain outstanding.
- Production remains untouched and requires a separate migration plan.

**Release rule:** keep PR #69 in draft. No merge, production migration, or production deployment is authorised by this reconciliation note.
