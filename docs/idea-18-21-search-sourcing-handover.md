# AQERITH Section 4: Ideas 18–21 implementation handover

**Branch:** `feat/ideas-18-21-search-sourcing`  
**Draft PR:** https://github.com/venugopalc80/ATS/pull/72  
**Environment changed:** ATS-Staging only  
**Production:** No schema changes, merges or deployments performed.

## Implemented in this increment

### Idea 18 — Advanced Search & Saved Filters
- Added database-backed search for candidates, applications, jobs and candidate document metadata.
- Filters include query text, skills, location, experience range, status, source, recruiter and date range where the record type supports them.
- Query values are parameterised; search wildcard characters are escaped. General search does not match candidate email, phone, resume text or internal notes.
- Saved searches store versioned JSON criteria, not executable SQL fragments. Criteria are revalidated on execution.
- Shared searches require organisation admin access; saved-search results are owner/shared scoped.
- Added a search workspace at `/search`.
- Added structured indexes for status/date, experience, source, recruiter, skill arrays and document date.
- Saved-search alerts are deliberately rejected until a notification worker exists.

### Idea 19 — Talent Pools & Candidate Segmentation
- Added tenant-scoped pools, many-to-many candidate memberships, candidate tags and tag assignments.
- Membership rows include purpose, processing basis, expiry, actor and membership history. Candidate records are not copied.
- Adding a candidate checks organisation membership, `do_not_contact` status and candidate retention expiry.
- Expired/retention-expired and `do_not_contact` memberships are transitioned and audited when a pool or its members are listed.
- Added pool management UI at `/talent-pools` and backend APIs for tags.
- Processing-basis choices are generic product metadata, not a substitute for jurisdiction-specific legal review.

### Idea 20 — Candidate Sourcing & Import Management
- Added CSV preview, header mapping, server-side validation, duplicate detection, row-level results and an explicit commit endpoint.
- Candidate records retain `source_id` and `import_batch_id`; import batches retain source, uploader, filename, SHA-256, status and row counts.
- Added an import workspace at `/imports`, including row-level validation feedback.
- Current limits: UTF-8 CSV only, 5 MB maximum, 1,000 rows per batch. Preview/commit runs synchronously.
- Original CSV bytes are not retained; only the filename, checksum and mapped row snapshots are stored. No malware-scanning provider is configured. Do not expand accepted upload types or retain raw files until scanning/storage controls are implemented.

### Idea 21 — Referrals & Recruitment Campaigns
- Added campaign, channel, referral, campaign-membership and campaign-event tables.
- Added campaign creation/status controls, channel creation, referral entry and auditable referral status correction.
- Campaign metrics define qualified applications as attributed applications in submitted/interview/offer/hired stages, interview progression as interview/offer/hired, and hires as hired applications.
- Channel spend includes currency. Aggregate spend/cost-per-hire is returned only when recorded spend uses one currency; cost per hire uses applications explicitly linked through campaign attribution.
- Metrics remain an initial workspace, not a complete analytics dashboard. First-touch/last-touch attribution automation and non-referral campaign source integrations remain outstanding.

## Database migrations

- `20261022130000_search_sourcing_features.sql`
- `20261022133000_sourcing_link_integrity.sql`
- `20261022140000_search_indexes.sql`
- `20261022141000_sourcing_browser_grant_hardening.sql`
- `20261022142000_campaign_channel_spend_currency.sql`
- `20261022143000_talent_pool_processing_basis.sql`
- `20261022144000_sourcing_api_only_access.sql`

The migrations were applied to ATS-Staging. Verification found 14 expected sourcing tables, RLS enabled on all 14, 10 search indexes present, and no direct `anon`/`authenticated` table grants on the sensitive sourcing tables. The migration history contains the sourcing migration and follow-ups.

A rollback-transaction SQL smoke test created temporary tenant A/B records and confirmed that cross-tenant candidate-to-pool membership, candidate-to-tag assignment, referral/application linkage, and campaign-to-job linkage were rejected. The transaction rolled back; a separate check found no temporary smoke-test organisation remaining.

## Verification status

- [x] Feature branch created from `main`.
- [x] Draft PR #72 opened.
- [x] Staging schema migrations applied.
- [x] Staging table/RLS/index/grant checks completed.
- [x] Cross-tenant link-integrity smoke test passed in a rolled-back transaction.
- [ ] Python unit tests executed. Tests are committed, but no test runner was available through the connected workflow.
- [ ] Frontend typecheck/build and authenticated browser acceptance.
- [ ] Full API integration tests for role checks, import replay, saved-search ownership and pool expiry.
- [ ] Record-level permission model integrated. Current code restricts broad sourcing APIs to recruiter/admin roles and applies pool ownership checks, but does not yet implement per-record ACLs for every search result.
- [ ] Background queue for large imports and saved-search notification delivery.
- [ ] Malware scanning/private raw-file retention workflow.
- [ ] Navigation links from the main app shell.
- [ ] Production schema compatibility review and deployment acceptance.

## CI and deployment

The PR's current Vercel status checks failed with the platform's build-rate-limit/upgrade message. They did not provide a successful application build result. The new focused GitHub Actions workflow is included in the branch, but it has not run on this draft PR. A local checkout was attempted for running Python/Node suites, but GitHub could not be reached from the connected runtime.

**Release decision:** keep PR #72 in draft. Do not merge or deploy to production until tests, build, record-level permissions, import handling and frontend acceptance checks pass.
