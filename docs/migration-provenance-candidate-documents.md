# Migration provenance review — candidate document schema

**Review date:** 2026-11-01  
**Repository:** `venugopalc80/ATS`  
**Branch:** `feat/section-6-analytics-bi`  
**Scope:** Read-only comparison of committed migrations and the connected staging schema. No database changes were made.

## Finding

The repository contains two migrations that both create `public.candidate_documents` and configure the private `candidate-documents` storage bucket:

- `supabase/migrations/20261012090000_candidate_documents.sql`
- `supabase/migrations/013_candidate_documents.sql`

They are not equivalent. Both use `CREATE TABLE IF NOT EXISTS`, so the first migration to create the table determines its actual column constraints and later creation attempts do not reconcile the table definition. Applying both does not guarantee the final schema matches either file.

## Differences that affect the resulting schema

| Area | Timestamped migration | Numbered migration |
|---|---|---|
| `document_type` allowed values | `cv`, `cover_letter`, `certificate`, `other` | `cv`, `cover_letter`, `portfolio`, `other` |
| SHA-256 validation | Explicit 64-character lowercase hex check | Non-empty text only |
| `uploaded_by` | Nullable UUID, no declared FK | UUID references `auth.users(id)` with `ON DELETE SET NULL` |
| SHA-256 lookup index | Organisation + SHA-256 partial index | Not defined |
| RLS policies | Enables RLS, defines no table policies | Enables RLS and defines member read, insert and update policies |
| Storage bucket | Private, 5 MB, PDF/DOCX | Same private bucket settings |

The timestamped migration's comments state that browser clients must not access the table or bucket and that API access is server-side. The numbered migration adds organisation-member policies. These access models must be reconciled with the actual application access path before any migration is changed.

## Read-only staging schema comparison (2026-11-01)

The connected staging schema was inspected through PostgreSQL catalog metadata. The live `candidate_documents` table currently has:

- Document types `cv`, `cover_letter`, `certificate`, `other`, matching the timestamped migration rather than the numbered migration.
- A lowercase 64-character SHA-256 check constraint.
- No foreign-key constraint on `uploaded_by`.
- The organisation/candidate/created partial index, organisation/SHA-256 partial index, and an additional organisation/created partial index.
- RLS enabled, with no table policies.
- Table-level `SELECT` privilege for `authenticated`, but no `INSERT`, `UPDATE` or `DELETE` privilege; `anon` has no `SELECT` privilege.
- A private `candidate-documents` bucket with a 5 MB limit and PDF/DOCX MIME allowlist. No matching direct Storage object policies were found.

This live shape is closer to the timestamped migration, but it is not an exact match because of the additional index. The catalogue cannot prove which historical SQL produced it. With RLS enabled and no table policies, the authenticated table grant does not by itself expose rows through the normal client role. The intended server-side service-role path must still perform tenant and user authorisation before metadata or file access. No access-policy changes were made.

## Why this matters

1. Migration order can produce different constraints and permissions on staging or a fresh installation.
2. `CREATE TABLE IF NOT EXISTS` does not add missing constraints, foreign keys, indexes or policies to an already-created table.
3. The two accepted document-type lists conflict: one supports certificates and the other portfolios.
4. The policies in the numbered migration may not match the server-only access model described in the timestamped migration.
5. The staging migration ledger stores version identifiers but not the original SQL text, so it cannot establish which definition was applied.

## Required reconciliation before schema work

1. Recover the exact migration SQL applied to each environment, or obtain a reviewed schema dump including constraints, indexes, policies, grants and storage bucket configuration.
2. Inspect application routes and storage access to establish whether document metadata is intentionally server-only or directly accessible to authenticated tenant members.
3. Agree one canonical document-type vocabulary and one authoritative `uploaded_by` integrity rule.
4. Compare the live schema to the canonical definition in an isolated database.
5. Create a forward-only, reviewed migration for any required differences. Do not edit historical migrations that may already have been applied.
6. Verify RLS, grants, storage policies, cross-tenant isolation and upload/download flows with tests before staging rollout.

## Safety status

All staging checks in this review were read-only catalogue queries. No DDL, DML, migration-ledger edits, grants, RLS policies or Storage settings were changed. The candidate-document schema conflict is an additional migration-provenance blocker for reproducible environments; the current catalogue snapshot does not establish that the live staging schema is broken or publicly exposed.


## Saved analytics report schema added on the feature branch

A new forward-only migration, `supabase/migrations/20261101180000_saved_report_definitions.sql`, now defines a dedicated `saved_report_definitions` table. It stores organisation, creator, report type, validated filter JSON, sharing state and timestamps. It does not reuse saved searches or organisation settings.

The migration uses the existing `is_org_member` and `is_org_admin` helpers. Private reports are visible to their creator; shared reports are visible to organisation members. Only organisation admins can enable or change sharing. The backend independently checks membership and report ownership/admin rights.

**Important:** this migration is committed to the feature branch only. It has not been executed against staging. Before applying it, reconcile the existing migration history and validate the migration against a clean isolated database and a reviewed staging schema snapshot.


## Saved report implementation notes (2026-11-01)

- Added tenant-scoped saved report CRUD API and a dedicated forward-only migration for `saved_report_definitions`.
- Supported report types match the CSV export contract, including `campaign_roi`.
- Private reports are visible to their creator. Organisation admins can view/manage tenant reports; only admins can change sharing state. Organisation members can see shared reports.
- Saved filter JSON is a typed allowlist of date range, job and recruiter IDs. Unsupported date/job filters for workload and forecast are rejected at save/update time.
- Added a Saved Reports panel to Analytics to save a private report setup, apply a saved setup and delete a saved report.
- The migration remains unexecuted in staging pending migration provenance reconciliation and isolated-database validation.
