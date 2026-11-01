# Migration provenance review — candidate document schema

**Review date:** 2026-11-01  
**Repository:** `venugopalc80/ATS`  
**Branch:** `feat/section-6-analytics-bi`  
**Scope:** Read-only comparison of the two committed candidate-document migration files. No database changes were made.

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

This review was performed from committed repository files only. It did not query or modify staging data, execute DDL, alter migration history, or change storage settings. The candidate-document schema conflict is an additional migration-provenance blocker for reproducible environments; it is not evidence by itself that the live staging schema is currently exposed or broken.
