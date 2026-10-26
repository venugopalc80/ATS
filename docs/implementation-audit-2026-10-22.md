# AQERITH Implementation Audit — Snapshot (2026-10-22)

## Purpose and confidence

This is an initial repository-backed audit snapshot, not the final 49-idea completion score. It distinguishes code/branch evidence from acceptance-tested and production-verified functionality. A drafted PR or a feature branch is **not** counted as complete.

**Repository:** https://github.com/venugopalc80/ATS  
**Audited baseline:** `main` at `a4960fc290c9759792667363649966f60ff79994`  
**Production domain recorded in project notes:** https://aqerith.com  
**Rule:** No production migration, merge, or deployment is authorised by this audit.

## Initial findings

1. The baseline contains a FastAPI backend, Next.js frontend, Supabase migrations, authentication/organisation membership checks, candidate/job/application/document routes, workflow services and audit-related migrations.
2. Several feature branches and draft PRs contain substantial proposed work, but their presence does not prove the work is integrated into `main`.
3. There are overlapping implementation tracks for the application pipeline (PRs #69 and #70) and chained PRs that target other feature branches rather than `main` (#58, #59, #64). These require dependency/merge-order review to avoid duplicate or stranded changes.
4. The current CI run for Idea 03 was observed in progress during this snapshot; the result must be rechecked before acceptance.
5. The complete canonical 49-title roadmap has not yet been located as one version-controlled source. Only ideas with explicit evidence below are listed; unverified titles are deliberately not invented.

## Evidence-backed roadmap snapshot

Status definitions:
- **Foundation exists** — related source code or schema is present on the inspected baseline.
- **Draft implementation** — a proposed feature branch/PR exists but is not accepted into main.
- **Partial / verify** — some related functionality exists; full acceptance criteria have not been proven.
- **Not audited** — insufficient evidence to assign a completion status.

| Idea | Feature | Snapshot status | Evidence / remaining gate |
|---:|---|---|---|
| 01 | Dashboard / recruiter command centre | Partial / verify | Dashboard routes and prior dashboard work exist; several open PRs (#50–#52, #58) mean acceptance/integration needs review. |
| 02 | Jobs & requisitions | Draft implementation | PR #59 open; targets a feature branch rather than main. |
| 03 | Candidates & Talent Pool | Draft implementation | PR #60 open; CI was in progress; browser QA, tenant isolation and privacy acceptance still required. |
| 04 | Applications & Recruitment Pipeline | Draft implementation | PRs #69 and #70 overlap; PR #70 adds stage history/transition API, but tests and migration have not been run per its PR body. |
| 05 | Application Forms & Candidate Self-Service | Draft implementation | PR #62 open; validate form versioning, server validation, accessibility, secure uploads and duplicate handling. |
| 06 | CV Parsing & Document Intelligence | Partial / verify | Document upload and bulk CV import history exist; PR #61 open for parsing work, with extraction review, provenance and retry safety to verify. |
| 07 | Candidate Matching & Job Fit Intelligence | Draft implementation | PR #76 open for responsible-AI foundations; matching evidence, versioning, quality and fairness remain to be verified. |
| 08 | Recruitment Workflow Automation | Draft implementation | PR #63 open; verify idempotency, execution history, permissions, retries and emergency disable. |
| 09 | Not confirmed from canonical roadmap | Not audited | Need source-of-truth title and acceptance criteria. |
| 10 | Interview Kits & Structured Scorecards | Draft implementation | PR #64 open; base is another feature branch, so integration order must be resolved. |
| 11 | Candidate Assessments & Skills Testing | Draft implementation | PR #65 open; automated checks and full acceptance not verified. |
| 12 | Offer Management & Approval | Draft implementation | PR #66 open; approval, permissions and lifecycle tests not verified. |
| 13 | Recruitment Documents & E-signatures | Draft implementation | PR #67 open; provider/signature and audit integration not verified. |
| 14 | Communication Hub & Notification Preferences | Draft implementation | PR #68 open; delivery, retries, preferences and audit behaviour not verified. |
| 18–21 | Search, talent pools and sourcing | Draft implementation | PR #72 open; CI verification PRs #74–#75 are closed without merge. Inspect results and source branch before acceptance. |
| 28 | Recruitment Analytics & KPI Dashboard | Not audited end-to-end | Existing dashboard/analytics code may support parts; metric definitions and calculation correctness need tests. |
| 34 | AI Recruitment Assistant | Draft implementation | PR #76 is labelled Section 7 responsible-AI foundations; do not treat this as proof the assistant is complete. |
| 40 | Privacy, Consent & Data Rights Management | Draft implementation | PR #77 open; retention execution, rights-request fulfilment, identity verification and operational recovery remain stated gaps. |
| Other ideas | Remaining roadmap items | Not audited | Locate canonical 49-idea tracker and map every item to code, PRs, tests, migrations and deployment evidence. |

## Open PR / integration risks observed

- **Idea 04 duplicates:** #69 and #70 both describe application stage transitions. Choose a single canonical implementation or explicitly consolidate them before merge.
- **Chained bases:** #58 → dashboard branch; #59 → recruiter tasks branch; #64 → interview scheduling branch. Confirm merge dependencies and avoid assuming these PRs are independently mergeable.
- **Many draft PRs:** Ideas 01–14, Section 4, Section 5, Section 7 and Section 8 contain work that has not been accepted into main as of this snapshot.
- **Security work is not release proof:** migration files and policy code must be tested against a disposable database; do not apply new migrations to production as part of this audit.
- **Production state:** This snapshot does not independently verify current production deployment health or live database migration state.

## Next audit steps

1. Locate and pin the canonical 49-idea roadmap (IDs, names, acceptance criteria, dependencies).
2. Inventory all PRs/branches and classify each as merged, open, closed-unmerged, duplicate, or superseded.
3. Compare main and proposed branch files against each idea's acceptance criteria.
4. Run available CI and targeted tests; record exact results and blockers.
5. Review migrations and tenant/role access on a disposable database.
6. Verify preview UI/API behaviour where credentials and environments permit.
7. Calculate completion using weighted acceptance criteria, not branch count or code volume.
8. Publish the final 49-row tracker with status, evidence links, confidence, owner/dependency, and next action.

## Completion calculation rule

For each idea, score acceptance criteria individually:
- Pass = 1
- Partial = 0.5
- Fail / not implemented = 0
- Not verified = excluded from the *verified* numerator and explicitly reported as unknown, not silently counted as complete.

Report both:
- **Verified completion** = passed criteria / all required criteria.
- **Evidence coverage** = criteria with a reviewed result / all required criteria.

Do not assign an overall percentage until the canonical list and criteria for all 49 ideas are reconciled.


## Live repository queue snapshot (checked 2026-10-22)

The latest GitHub query returned **42 open pull requests**, of which **34 are drafts**. **6 target a base branch other than `main`**, so they cannot be treated as standalone changes ready to land. This is a repository-queue count, not a feature-completion count.

### Immediate blockers to orderly delivery

1. **Consolidate duplicate application-stage work.** PRs #69 and #70 both cover Idea 04. Pick one canonical path and close/supersede the duplicate only after checking the unique changes.
2. **Resolve branch dependencies before acceptance.** Several PRs target feature branches, including #58, #59 and #64. Rebase or sequence them deliberately; do not merge a dependent PR ahead of its base.
3. **Do not treat open PRs as completed roadmap items.** Drafts for Ideas 01–14 and Sections 4, 5, 7 and 8 are implementation candidates. Each needs its own acceptance evidence and a deliberate integration order.
4. **Finish the canonical 49-idea inventory.** The project notes and repository evidence currently do not establish one complete, version-controlled source containing all 49 titles and acceptance criteria. Until it is found, the overall percentage remains unverified.
5. **Check live deployment separately.** Vercel READY preview deployments exist for some feature branches, but that does not establish that `aqerith.com` is running those commits or that their migrations are applied in production.

### Execution order

- **P0 — establish a release baseline:** identify the deployed production commit and current migration state; keep production unchanged during audit.
- **P1 — reduce integration ambiguity:** choose the canonical Idea 04 PR, map chained PR bases, and pin the roadmap source.
- **P2 — close the current high-risk implementation gates:** tenant/resource permissions, secure imports, workflow transition tests, and privacy/AI safety gates.
- **P3 — accept features in dependency order:** require CI, migration review, tenant-isolation tests and authenticated preview QA for each integration.
- **P4 — calculate the score:** score all 49 ideas against their acceptance criteria and publish both verified completion and evidence coverage.

No PR was merged or closed by this audit update, and no production migration or deployment was performed.


## Follow-up verification (2026-10-22, after initial snapshot)

### Production deployment evidence

- Vercel's latest deployment query for project `ats`, filtered to production, returned a **READY** deployment from `main` at commit `6d9fbcb4214c25d2fc8770e515b10c22038eec97` ("fix: keep active organisation selection consistent").
- Deployment inspector: https://vercel.com/the-pixel-muses/ats/2o6UhYMCG3GPnRZxBbEuJcSzLNfD
- This verifies the Vercel project's production deployment record, not the custom domain's DNS/routing, backend service deployment, or production database migration parity. Those remain separate checks.

### Idea 04 duplicate-PR comparison

- **PR #69** head `feat/idea-04-application-pipeline`, SHA `607396414c53e124a01c57a6dcc82f786d58d680`, base `main`. It contains the dedicated transition/history endpoints, service logic, unit tests, and migration. Its body reports a staging-only SQL smoke test, but also says tests have not yet been executed in a proper repository checkout and the migration was applied outside migration history.
- **PR #70** is another draft from `main` for the same core capability. Its body says automated tests and migration execution have not been run and it has not been applied to a database.
- **Recommendation:** use #69 as the lead candidate for a technical acceptance review because it has stronger stated staging evidence; do not merge it yet. First reconcile the staging-only SQL with the committed migration and migration history, run backend tests and static checks, add authenticated tenant-isolation/API tests, and confirm the configured stage definitions are actually enforced. Only then decide whether #70 has any unique changes worth cherry-picking; otherwise mark it superseded after the canonical path is accepted.
- No PR was merged or closed and no production database or deployment was changed during this follow-up.


## Roadmap source discovery and Idea 04 acceptance scoring (2026-10-22)

A project Library brief titled `Pasted text(3).txt` supplies detailed acceptance criteria for Ideas **04–08**. This improves source coverage, but it is not the full 49-idea canonical index. The full 49-row roadmap and criteria still need to be assembled from authoritative project briefs and reconciled before publishing a product-wide completion percentage.

### Idea 04 — Applications & Recruitment Pipeline

Using the six acceptance criteria in the feature brief and current evidence:

| Acceptance criterion | Current evidence | Score |
|---|---|---:|
| Applications remain separate from candidate profiles | Separate `applications` entity references candidate and job IDs | Pass (1) |
| Invalid stage transitions rejected by backend | Transition validation and unit tests; relevant CI backend job passed | Pass (1) |
| Every transition is auditable | Stage-history trigger and staging smoke test reported; migration-history reconciliation still outstanding | Partial (0.5) |
| Tenant isolation is tested | Authenticated cross-tenant/API test evidence not yet supplied | Not verified (0) |
| Bulk actions report partial failures accurately | No accepted evidence for bulk pipeline actions | Not implemented / not verified (0) |
| Candidate-facing status is separated from internal status | No accepted evidence for the required separation | Not verified (0) |

**Provisional Idea 04 acceptance score: 2.5 / 6 = 41.7% evidenced; 58.3% remains unpassed or unverified.** This is a criterion score for Idea 04 only, not the whole product. It is deliberately conservative and should be updated when more code/tests are reviewed. The pipeline board, configurable stage definitions, bulk operations and SLA monitoring are also still required by the feature brief, so this score is not a claim that Idea 04 is release-ready.

### Progress reporting convention

Until the complete 49-idea criteria inventory is reconciled, each update should report:
1. **Idea-level completion** only when criteria can be scored with evidence.
2. **Roadmap evidence coverage** separately from implementation completion.
3. **Product-wide completion** as *not yet verified*, rather than inventing a precise percentage from PR counts.

Current roadmap evidence coverage: detailed acceptance criteria located for Ideas 04–08 (**5/49 = 10.2%** of the idea IDs). This is documentation coverage, not implementation completion.


## Idea 04 follow-up: API hardening and live database-state check (2026-10-22)

### Code and CI

- PR #69 now blocks status changes through generic `PATCH /api/applications/{id}` and directs callers to the dedicated transition endpoint. This closes the path that could change a stage without supplying the transition reason.
- The transition API schema now requires a non-blank reason (1–1,000 characters) and trims surrounding whitespace.
- Regression tests cover direct-PATCH rejection, required reason, and blank reason validation.
- GitHub Actions run #533 passed on head `7801d9c983113426ab07f9fa6f5c4e74c3c9171c`: backend unit tests, frontend TypeScript typecheck, and frontend production build. Run: https://github.com/venugopalc80/ATS/actions/runs/39807051098
- Vercel preview checks remain failed due to the team's build-rate-limit status, so no preview UX verification is claimed.

### Read-only database evidence

- **ATS-Staging** project `riauyrhfnlsxmtgipuxi`: `public.application_stage_history` exists; `public.application_stage_config` does not. The Supabase migration ledger has no application-stage migration entry. The history table was therefore created outside the committed migration ledger and must be reconciled before release.
- **ATS** production project `olsziyaepfesjtkceuzo`: neither `public.application_stage_history` nor `public.application_stage_config` exists in the inspected schema. Its migration ledger has no application-stage migration.
- These were read-only metadata/schema checks. No migration was applied to either database and no production data was changed.

### Current Idea 04 score

The acceptance score remains **2.5/6 = 41.7% evidenced**, with **58.3% not passed or not verified**. The API/CI gates have improved, but do not inflate the score while tenant-isolation API tests, migration reconciliation/application testing, bulk-operation partial-failure handling, candidate-vs-internal status separation, and full pipeline/SLA behaviour remain unverified or incomplete.

### Next safe action

1. Review the committed migrations against the existing staging history table and confirm migration filename/version conventions.
2. Test migrations 014 and 015 in a disposable PostgreSQL database, including fresh install, re-run/partial-state behaviour, triggers, RLS and organisation seeding.
3. Add authenticated API tests for cross-tenant access and admin-only stage configuration changes.
4. Only after those pass, apply through the tracked migration mechanism to **ATS-Staging**, then run authenticated preview QA. Do not touch production until staging acceptance and release approval are complete.


### Staging schema comparison follow-up

A further read-only inspection of ATS-Staging confirmed:
- The existing `application_stage_history` table has the expected eight columns from migration 014.
- The expected member-read and member-insert policies are present.
- Both application insert and status-update history triggers are present.
- RLS is enabled, and `anon` and `authenticated` have no direct SELECT or INSERT grants on the history table.
- The committed migration is still not represented in the Supabase migration ledger. Treat the live staging object as manually provisioned/drifted until that history is reconciled; do not blindly reapply or mark it as tracked.
- `application_stage_config` is absent from staging and production, so migration 015 has not been applied to either environment.


### Latest CI and data readiness (2026-10-22)

- PR #69 head `846ba70ee5eae304569cd6aa62825e1beec00662`: GitHub Actions run #539 passed backend unit tests, frontend typecheck and frontend production build. Run: https://github.com/venugopalc80/ATS/actions/runs/39807441180
- Read-only aggregate queries returned **zero application rows in both ATS-Staging and ATS production**. Therefore no existing live application data was available to validate status compatibility, baseline history seeding, or a realistic end-to-end stage transition.
- This is a data-readiness gap, not proof that the schema is broken. Before staging acceptance, create isolated test fixtures under a controlled test organisation or use a disposable database, then verify create → transition → history, invalid transition rejection, and cross-tenant denial.


## Idea 04 follow-up implementation hardening (2026-10-22, latest checked head)

- PR #69 latest head: `4a8d7747442d0e28f5bc2a1a8f7d7aa0fa7c32b5`; still draft and unmerged.
- Closed another stage-bypass path: `ApplicationCreate.status` is now restricted to `"new"`, so a caller cannot create an application directly as `hired`, `rejected`, or another later stage. Added schema regression tests for default stage and rejection of `status="hired"`.
- Added defense in depth in `ApplicationService.transition_application`: reject non-string/missing, blank, and over-1,000-character reasons; trim valid reasons before setting the database audit context. Added service-layer tests for blank/overlong reasons and trimming.
- These are committed changes, **not yet CI-verified**: the GitHub workflow/status lookup returned no run/status for latest head at audit time. Do not mark the new tests as passed until a run is visible and green.
- The last known successful CI remains run #539 on the preceding head `846ba70ee5eae304569cd6aa62825e1beec00662` (backend unit tests, frontend typecheck, frontend production build).
- Database release gates are unchanged: staging has the history table without the corresponding tracked migration-ledger entry; stage configuration is absent from staging and production. No migration or production write was made.
- Idea 04 remains **41.7% evidenced / 58.3% pending** against the six provisional acceptance criteria. The new tests improve implementation hardening but do not substitute for isolated-database migration tests, authenticated tenant-isolation acceptance, bulk partial-failure handling, candidate/internal status separation, or SLA coverage.
- Whole product completion remains **not yet verified**. Detailed criteria coverage remains 5 of 49 ideas (10.2%); the remaining 44 ideas need source-of-truth criteria and equivalent review. This is evidence coverage, not implementation completion.


## Idea 04 follow-up verification (2026-10-23)

- Latest inspected PR #69 head: `bc72513a5358265fc495f35c7b9b405caa5a94c6`; PR remains draft and unmerged.
- GitHub Actions run #574 completed successfully on this head: backend unit tests, frontend TypeScript typecheck, and frontend production build passed. Run: https://github.com/venugopalc80/ATS/actions/runs/39844638048.
- Added stage-configuration invariant checks: enabled non-terminal stages must have at least one next stage; disabled non-terminal stages may have none; terminal stages cannot have outgoing transitions. Regression tests cover each case.
- The application-creation guard and service-level transition-reason validation remain present in the inspected branch. This closes two bypass paths at schema and service layers, with the latest unit suite green.
- Vercel checks remain failed due to the team's build-rate limit; no preview acceptance is available from those checks.
- Database gates remain open: staging contains `application_stage_history` without a corresponding tracked migration-ledger entry; `application_stage_config` is absent in staging and production. No migration was applied.
- Idea 04 stays **41.7% evidenced / 58.3% pending** against the provisional six-criterion score. Passing unit/CI checks improves confidence in code but does not replace disposable-database migration testing, authenticated tenant-isolation testing, bulk partial-failure handling, candidate-facing/internal status separation, or SLA coverage.
- Whole-product completion remains **not yet verified**. Detailed acceptance criteria coverage remains 5/49 ideas (**10.2% evidence coverage**, not implementation completion); the full roadmap still needs source-of-truth reconciliation and audit.


## Correction to previous Idea 04 snapshot (2026-10-23)

The earlier follow-up entry above was superseded by additional commits after that snapshot. The latest inspected PR #69 head is `bc72513a5358265fc495f35c7b9b405caa5a94c6`, not `4a8d7747442d0e28f5bc2a1a8f7d7aa0fa7c32b5`. Run #574 passed backend unit tests, frontend typecheck, and frontend production build on the newer head: https://github.com/venugopalc80/ATS/actions/runs/39844638048. The additional stage-configuration dead-end invariants and tests are included. Vercel checks still fail because of the team build-rate limit; no preview deployment was verified. The migration, authenticated tenant-isolation, and remaining workflow acceptance gates are unchanged.


## New service-boundary finding (2026-10-23, pending CI)

- A code-path review found that the HTTP PATCH endpoint rejected stage changes, but `ApplicationService.update_application()` itself still accepted status updates if called by another internal route/service. That could bypass the required transition reason and write an incomplete audit event.
- Fixed by rejecting any `ApplicationUpdate` payload containing `status` at the service boundary before opening a database connection. Stage changes must call `transition_application()`.
- Updated tests to retain coverage for ordinary source edits and explicitly assert that direct service-level status updates fail before database access.
- Commit: `ce979fa5fa4201f07863baf3e2f3f9b42b3e7178`. No workflow/status result was returned at the time of this check; this latest change is pending CI. The preceding head `bc72513a5358265fc495f35c7b9b405caa5a94c6` passed run #574.
- No database writes or deployment occurred. Idea 04 remains **41.7% evidenced / 58.3% pending** until CI and the remaining database/authenticated acceptance gates pass.


### Latest CI checkpoint for service-boundary fix (2026-10-23)

Run #576 is executing on commit `ce979fa5fa4201f07863baf3e2f3f9b42b3e7178`: the backend unit-test step completed successfully; frontend dependency installation is still running and typecheck/build are pending. Full CI is not yet green. Track: https://github.com/venugopalc80/ATS/actions/runs/39942271580.


## Current checkpoint (2026-10-25) — PR #69

This checkpoint supersedes the older pending-CI notes above where they describe the latest state. Earlier entries are retained as historical audit trail.

- Current PR #69 head is `b214379e5a09819360ecc74328102da341222f43`, base `main`; PR remains open, draft, and unmerged.
- GitHub Actions run #603 passed both jobs on the current head: backend unit tests and frontend checks (TypeScript typecheck and production build). Run: https://github.com/venugopalc80/ATS/actions/runs/40144082517.
- Current Vercel status checks for `ats`, `ats-staging-api`, and `aqerith` are pending. No preview or production behaviour is being claimed from these pending checks.
- PR #69 description was refreshed to reflect the current head, green CI, and remaining release gates.
- Duplicate PR #70 remains open/draft. File comparison confirms overlapping router, schema, service and stage-history migration changes; PR #69 has additional configurable transition graph enforcement, frontend changes, and the second stage-config migration. Do not merge both; retain #70 as a reference until its unique changes are reconciled.
- The latest source still requires isolated database migration tests, authenticated tenant-isolation tests, backend role/grant verification, candidate-facing confidentiality review, and bulk/SLA acceptance. ATS-Staging has an existing history table/triggers without a corresponding tracked migration-ledger entry; stage config remains absent in staging and production.
- No migration, production write, merge, or deployment was performed.

### Current score and reporting

- **Idea 04:** remains **41.7% evidenced / 58.3% pending** against the six provisional acceptance criteria. Green CI improves code confidence but does not close the outstanding acceptance criteria.
- **AQERITH overall:** **not yet verified**. Detailed criteria coverage remains **5/49 ideas (10.2% evidence coverage)**; this must not be presented as product implementation completion.

### Next actions

1. Keep PR #69 draft and verify migration 014/015 against an isolated PostgreSQL/Supabase instance.
2. Resolve staging schema/migration-ledger drift without blindly rerunning migration 014.
3. Add authenticated API integration tests for cross-tenant denial and admin-only configuration changes.
4. Inspect deployment checks again when they complete; do not trigger extra deployments merely to force a preview.
5. Once Idea 04 gates are satisfied, reconcile PR #70 and then move to the next roadmap idea with its source-of-truth acceptance criteria.


### Additional route-level authorization regression coverage (2026-10-25)

- Added `backend/tests/test_application_pipeline_api_authorization.py` on PR #69 at commit `5d860ead241bf19d65a88922dd685f550bdd5f68`.
- The new tests exercise the route functions and assert that a non-member is denied before the transition service is called, and a non-admin is denied before stage configuration is updated. These are mocked route-guard tests; they do not replace authenticated HTTP/database integration tests.
- CI run #604 is in progress on this commit. Backend dependency installation and frontend dependency installation were still running at the latest check; no pass is claimed for the new tests until the run completes.
- A fresh read-only staging check reconfirmed the history table's `application_stage_history_reason_length` constraint and the two stage-history triggers. The migration ledger query returned no rows for versions `014`, `015`, or `20261022120000`. Table grants show `service_role` and `postgres`, with no direct grants shown for `anon` or `authenticated`.
- This strengthens the drift diagnosis: staging's history objects and constraint exist but are not represented in the migration ledger. It is still unsafe to blindly reapply the migration or edit the ledger without a documented reconciliation plan.
- No database writes, migration, merge, or deployment occurred.


### CI result for route-level authorization tests (2026-10-25)

- Run #604 completed successfully on PR #69 head `5d860ead241bf19d65a88922dd685f550bdd5f68`: backend unit tests, frontend TypeScript typecheck, and frontend production build all passed. Run: https://github.com/venugopalc80/ATS/actions/runs/40144207046.
- The new tests cover route-level guard behaviour with mocked service methods: non-members cannot proceed to transition writes and non-admins cannot proceed to stage configuration writes. They are useful regression tests but are not full authenticated HTTP/database integration tests.
- Vercel `ats-staging-api` is successful for this commit; `ats` and `aqerith` status checks remain pending at the latest check.
- PR #69 description now reflects current head and CI #604. PR remains draft/unmerged; no database migration or deployment occurred.


## Checkpoint — 2026-10-26 morning

### Newly discovered and fixed: creation actor attribution

- Code review found that the authenticated recruiter application-creation route passed the payload to the service but did not pass the acting user ID. The database trigger therefore could record the initial stage event with a null actor, even though subsequent stage transitions carried the actor.
- Fixed the service boundary: `ApplicationService.create_application(payload, actor_user_id)` now sets transaction-local `app.actor_user_id` before inserting the application. The authenticated API route passes the authenticated `user_id`. Public careers submissions intentionally remain anonymous.
- Added a regression test asserting the actor setting is executed before the application insert and contains the authenticated user's UUID.
- Current PR #69 head: `68b7a7e5c48da05ab5f6f6217dc9bbd204a58222`.
- CI run #675 is in progress: backend test step completed successfully; frontend dependency installation was still running at the latest check. Prior head run #604 passed backend tests, frontend typecheck, and production build.
- Current Vercel status checks for `ats`, `ats-staging-api`, and `aqerith` are pending.
- PR #69 description was updated to reflect current head, the actor-attribution fix, and the accurate CI state.
- No database writes, migrations, merges, or deployments were performed.

### Current score

- **Idea 04:** **41.7% evidenced / 58.3% pending** against six provisional acceptance criteria. This bug fix improves audit correctness but does not yet close an entire acceptance criterion.
- **AQERITH overall:** completion remains **not yet verified**; detailed acceptance criteria reviewed for **5/49 ideas (10.2% evidence coverage)**, not product implementation completion.

### Next actions

1. Wait for run #675 and capture final backend/frontend conclusions.
2. Inspect Vercel checks when they settle; verify actual preview behaviour before accepting.
3. Continue migration test planning without applying to staging/production; resolve existing staging schema/ledger drift first.
4. Expand route tests into authenticated HTTP/database integration tests and check candidate-facing confidentiality.
5. Compare PR #70 for unique code worth porting into PR #69, then keep only one transition implementation.


### Final CI result for 2026-10-26 morning checkpoint

- GitHub Actions run #675 completed successfully on PR #69 head `68b7a7e5c48da05ab5f6f6217dc9bbd204a58222`: backend unit tests, frontend TypeScript typecheck, and production build all passed. https://github.com/venugopalc80/ATS/actions/runs/40308009510
- The PR description was updated with the passing run and the application-creation actor attribution fix.
- Vercel status checks for `ats`, `ats-staging-api`, and `aqerith` are still pending on the current head; no preview acceptance is claimed.
- No database migration/write, merge, or deployment occurred.


### Creation-route actor propagation regression (2026-10-26)

- Added a route-level test asserting the authenticated `user_id` is passed into `ApplicationService.create_application(payload, user_id)`; this complements the service-level test that checks `app.actor_user_id` is set before the SQL insert.
- Current PR #69 head: `8b98ca03b628ef5a12ef46312851bd4c278c86da`.
- CI run #677 is queued for the current head: https://github.com/venugopalc80/ATS/actions/runs/40308229057. Run #675 passed on the previous head, including backend tests, frontend typecheck and production build.
- Vercel checks on the new head are not yet confirmed. No migration, database write, merge, or deployment occurred.


## Stage-graph concurrency hardening (2026-10-26)

- Reviewed a potential race: concurrent stage configuration edits or an edit racing an application transition could validate against a stale organisation stage graph.
- Added a transaction-scoped PostgreSQL advisory lock keyed by organisation. Stage-configuration edits acquire it before selecting/updating configuration; application transitions acquire the same lock before reading the graph and validating the requested transition.
- Added a regression assertion that the transition lock is acquired before stage configuration is read.
- Code commits: service `c9c52cd6b2eb6f05eb768c8501772a093f57bb32`; test `cacf02c8a75a52a9629cef6d75d2c277fee27894`.
- GitHub Actions run #677 passed on the preceding head, not this new lock change. CI for current head remains pending verification. Vercel checks were green on the preceding head; current-head status must be rechecked.
- No database writes, migrations, merges, or production deployments were performed.

### Current score and next gates

- **Idea 04:** remains **41.7% evidenced / 58.3% pending** against six provisional acceptance criteria. This concurrency hardening improves correctness but does not close a full acceptance criterion.
- **AQERITH overall:** **not yet verified**; detailed acceptance criteria reviewed for **5/49 ideas (10.2% evidence coverage)**, which is not implementation completion.
- Next: verify CI and Vercel on the current head; then pursue isolated PostgreSQL migration tests and authenticated tenant-isolation tests. Keep PR #69 in draft and do not apply migrations to staging or production while staging schema/migration-ledger drift remains unresolved.


### Current-head CI and Vercel check (2026-10-26, 11:11 UTC)

- Current PR #69 head `cacf02c8a75a52a9629cef6d75d2c277fee27894`; GitHub Actions run #692 is in progress.
- GitHub Actions run #692 subsequently completed successfully: backend unit tests, frontend TypeScript typecheck, and frontend production build all passed. Run: https://github.com/venugopalc80/ATS/actions/runs/40312978591.
- Current-head Vercel status checks for `ats`, `ats-staging-api`, and `aqerith` are failing with the team's build-rate-limit status. This is not evidence of an application build failure, but it prevents preview acceptance.
- No database writes, migrations, merges, or production deployments occurred.


## Disposable PostgreSQL migration smoke-test harness (2026-10-26)

- Added `backend/tests/test_application_stage_migrations.py`. It refuses to reset a database unless its name is exactly `aqerith_migration_test`, then bootstraps the minimum Supabase-like auth/tenant schema needed to execute the actual Idea 04 migration files.
- The smoke test applies `20261026120000_application_stage_history.sql` and `20261026120100_application_stage_config.sql` twice, then checks:
  - baseline history for an application predating the migration;
  - ten default stages for existing and newly created organisations;
  - actor attribution on application creation;
  - actor and reason attribution on stage change;
  - RLS enabled and no direct SELECT grants to `anon` or `authenticated` for history/config tables.
- Updated `.github/workflows/dashboard-update-1-acceptance.yml` to provision a PostgreSQL 16 service and run this test alongside the backend suite; migration paths now trigger the workflow.
- Test harness commit: `8287c48fc35674c710c370b9981c6c932e582cad`; transaction-local-setting correction: `13028d68c11eaa886adda70f9e35d5c83ae2b130`; workflow update commit: `765efd6eaa36badecb6a7ac2a2df4db491235b0b`.
- CI run #692 passed before this harness was added. Runs #697/#698 for earlier commits in this change set are still in progress; current-head CI has not yet been verified.
- No Supabase project was created, no database migrations were applied to staging/production, and no production data was modified.


### Migration smoke-test first-run correction (2026-10-26)

- Run #697 executed the real migrations twice in PostgreSQL 16 and reached the application-created history assertion. The only reported failure was a test expectation type mismatch (psycopg returns a UUID object; the assertion expected a string), not a migration SQL error. Run: https://github.com/venugopalc80/ATS/actions/runs/40320818797.
- Corrected the expected actor type to `UUID` in commit `46dd9286fb3f698eadf1e31283b9d1ca5c79695c`.
- Current run #721 is queued for that corrected head. Do not call the migration smoke test green until the rerun completes successfully.
- Vercel checks still fail because of the team build-rate limit. No staging/production database changes occurred.


### Partial-state migration test added (2026-10-26)

- Extended the disposable PostgreSQL smoke test to remove the stage-history update trigger and one seeded stage row after initial migration, then rerun migrations and verify both are restored.
- This covers partial-state repair in addition to rerun/idempotency. Current code commit: `3cca5999ba26a246d274f782f8f98f6ec05ace17`.
- The UUID assertion correction is included. Run #721 is still executing on an earlier head; current-head CI is pending.


### Migration fixture fidelity improvement (2026-10-26)

- Updated the disposable migration-test fixture to mirror the core schema's unique `(job_id, candidate_id)` application constraint.
- The post-migration trigger test now uses a separate job/candidate pair instead of relying on an unrealistic duplicate application.
- Commit: `3204ac58af9080122fb24c73d09e3964fca2c771`. Current-head CI is pending.


### Deterministic history assertion correction (2026-10-26)

- The PostgreSQL smoke test successfully exercised migration rerun/partial-state repair and reached the transition-history assertion, but that assertion assumed `created_at desc` always yields the just-inserted event. PostgreSQL `now()` is transaction-stable, so creation and transition events in the same transaction can share a timestamp.
- Fixed the test to select the expected transition by its unique reason (`CV reviewed`) instead of relying on timestamp ordering.
- Run #723 failed only at that assertion after the preceding migration and trigger checks had progressed; current fix commit: `61831d18713c6998a5e9e6d29b69c7937f7babd3`. New CI is pending.


### PostgreSQL migration smoke test passed (2026-10-26)

- Run #724 backend job passed, including all backend unit tests and the disposable PostgreSQL 16 migration smoke test.
- The smoke test now verifies both timestamped migrations can be applied, that rerunning after deliberately dropping the stage-history update trigger and deleting the `screening` stage restores both, that existing applications receive a baseline history row, that authenticated backend actor/reason context is captured, that existing/new organisations receive ten stages, and that browser roles have no direct SELECT grants while RLS is enabled.
- Run #724 frontend typecheck also passed; production build was still in progress at the latest poll. Run: https://github.com/venugopalc80/ATS/actions/runs/40321305007.
- Vercel preview checks remain blocked by the team's build-rate limit. No staging/production migrations or writes occurred.


### Full CI green after migration smoke-test addition (2026-10-26)

- Run #724 completed successfully: backend unit tests, PostgreSQL 16 migration smoke tests, frontend TypeScript typecheck, and frontend production build all passed.
- This is the first green run that exercises the actual timestamped Idea 04 migration files against disposable PostgreSQL and verifies rerun/partial-state recovery.
- Run: https://github.com/venugopalc80/ATS/actions/runs/40321305007.
- Vercel checks for `ats`, `ats-staging-api`, and `aqerith` remain blocked by the team's build-rate limit; no preview UX acceptance is claimed.


### HTTP-level authorization and public response privacy checks (2026-10-26)

- Added `backend/tests/test_application_pipeline_http_authorization.py` on PR #69 to exercise the real FastAPI router and response handling for:
  - cross-tenant application reads returning 403;
  - cross-tenant stage-history reads being denied before the history service is called;
  - cross-tenant transitions being denied before the transition write;
  - non-admin stage-configuration writes being denied before the configuration service is called.
- These tests override the authenticated-user dependency and mock organisation membership/service boundaries. They are stronger than direct function-only tests because requests pass through FastAPI routing and response serialization, but they are **not** live Supabase-authenticated or database-backed tenant-isolation tests.
- Added a public careers submission response-contract assertion: anonymous submission responses contain only `success`, `application_id`, and `message`; recruiter-only matching/review fields are not returned by that endpoint.
- Current PR #69 head: `381978574a656a182b767da15fadd83bfeff17a5`. Current-head CI run #760 passed both jobs, including backend unit tests, the disposable PostgreSQL 16 migration smoke test, frontend typecheck, and production build: https://github.com/venugopalc80/ATS/actions/runs/40349860950.
- Vercel status checks for `ats`, `ats-staging-api`, and `aqerith` remain blocked by the team's build-rate limit. Preview UX acceptance is not claimed.
- No staging/production migrations or data writes, merge, or production deployment occurred.

### Current Idea 04 score and remaining gates (2026-10-26)

- **Idea 04 remains 41.7% evidenced / 58.3% pending** against the six provisional acceptance criteria. Additional green regression tests increase confidence but do not close the remaining acceptance criteria.
- **AQERITH overall completion remains unverified.** Detailed acceptance criteria have been reviewed for 5/49 ideas (10.2% audit coverage), which is not implementation completion.
- Remaining release gates: live authenticated DB/API tenant-isolation tests; staging migration-ledger drift reconciliation; confirmation of backend-vs-browser database privileges; broader candidate-facing confidentiality review; bulk assignment/stage actions and SLA monitoring; reconcile overlapping draft PR #70; Vercel preview acceptance.


### Disposable-PostgreSQL tenant membership exercised through FastAPI (2026-10-26)

- Added `backend/tests/test_z_application_database_membership_http.py`. It runs after the disposable migration smoke test in CI and uses the same PostgreSQL 16 test database; it does not connect to staging or production.
- The test suite uses real `organization_members` rows and the real `get_org_role` database query while sending requests through FastAPI's TestClient. Application lookup is mocked so this isolates the authorization boundary rather than claiming a full database-backed application CRUD test.
- Verified that a user without membership in the application's organisation receives 403 on application read and transition; the transition service is not called. Verified that a recruiter role receives 403 for stage-configuration writes before the write service is called.
- First run #761 failed because the test imported `TestClient` from the wrong module. Corrected the import to `fastapi.testclient`; no application code or database migration was changed to address that test-only failure.
- Current PR #69 head: `7c0d70cb6669a75f8a57bb9c90a6e05a2fada1ae`. Run #762 passed: 54 backend tests (4 skipped because they require optional environment/setup), PostgreSQL migration smoke tests, frontend typecheck, and frontend production build: https://github.com/venugopalc80/ATS/actions/runs/40350562461.
- This closes the narrow CI-tested membership-role gate for Idea 04, but it does **not** prove live Supabase JWT validation, real Supabase RLS behaviour, or all tenant-isolation paths. Those remain release gates.
- Vercel checks remain blocked by the daily build-rate limit; preview/runtime acceptance is still pending. No staging/production database writes, migrations, merge, or deployment occurred.

### Updated Idea 04 score (2026-10-26)

- **Idea 04 remains 41.7% evidenced / 58.3% pending** against the six provisional acceptance criteria. The new disposable-database membership tests add useful evidence but do not close a whole acceptance criterion.
- **AQERITH overall completion remains unverified**; 5/49 ideas have detailed acceptance-criteria evidence (10.2% audit coverage), not product completion.


### Staging/production migration drift recheck (read-only, 2026-10-26)

- Rechecked the **current renamed migration versions** against both Supabase projects after the PR branch moved the migration timestamps.
- ATS-Staging (`riauyrhfnlsxmtgipuxi`):
  - `public.application_stage_history` exists; `public.application_stage_config` does not.
  - The latest migration ledger entry at/after the inspected cutoff is `20261026143744:section9_support_content_scope`; neither Idea 04 migration is recorded.
  - The current `applications_status_check` still allows only `new`, `screening`, `submitted`, `interview`, `offer`, `hired`, `rejected`, and `withdrawn`. It does not yet allow `shortlisted` or `assessment`.
  - Read-only privilege checks report `service_role` can SELECT stage history and `authenticated` cannot. The config-table grant check is not applicable while that table is absent.
- Production (`olsziyaepfesjtkceuzo`):
  - Neither `application_stage_history` nor `application_stage_config` exists.
  - The same legacy application status constraint remains; no migration-ledger entries at/after the inspected cutoff were returned.
- **No SQL writes were executed.** These queries were read-only.

#### Safe reconciliation proposal (not executed)

1. Export and preserve the current staging definitions for the history table, its constraints/indexes, policies, trigger function/triggers, grants, and migration ledger; keep this snapshot with the release record.
2. Compare the captured definitions to `20261026150000_application_stage_history.sql`. Existing staging objects appear to match the intended objects, but the ledger does not attest that the migration ran. Do not manually insert a ledger row.
3. In a controlled staging release window, run the tracked history migration through the normal Supabase migration workflow only after a reviewer confirms its idempotent `IF NOT EXISTS`/drop-and-recreate operations are compatible with the captured schema. Verify the migration ledger entry, object definitions, baseline history, RLS, and grants immediately afterwards.
4. Apply `20261026150100_application_stage_config.sql` to staging only after step 3 passes. Verify the status constraint includes all ten supported statuses, ten stage rows per existing organisation, trigger-based seeding for a newly created test organisation, and expected service-role/browser-role privileges.
5. Run staging API regression tests, including a transition into `shortlisted` and `assessment`, before considering production. For production, use the same ordered migrations in an approved release window with backup/rollback planning; no migration has been authorised or run here.

This remains a proposal only. Production/staging schema changes require explicit release approval.
