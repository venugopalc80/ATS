# AQERITH 49-Idea Delivery Tracker

**Baseline date:** 2026-10-22  
**Repository:** https://github.com/venugopalc80/ATS  
**Baseline branch:** `main`  
**Baseline commit:** `a4960fc290c9759792667363649966f60ff79994` (reported by current open PR base snapshots; confirm against live HEAD before release decisions)  
**Purpose:** Measure delivery from evidence, not from PR count or the existence of code on a feature branch.

## Rules for status and completion

Each roadmap idea must be assessed against its own canonical acceptance criteria. Use the following status values:

- **Unassessed** — canonical scope or evidence has not yet been reconciled.
- **Planned** — scope agreed, implementation not evidenced.
- **In progress** — code exists on a branch/PR but acceptance is incomplete.
- **Implemented, unverified** — implementation is present, but required checks are missing.
- **Verified in staging** — acceptance checks pass in staging with evidence recorded.
- **Released** — merged to `main`, deployed to the intended environment, and smoke-tested against the deployed commit.
- **Blocked** — a named dependency or unresolved failure prevents progress.

A PR, migration file, passing unit test, or READY preview alone does not make an idea “Released”. Record production status only when the deployed commit and runtime behavior are verified.

## Evidence-based completion calculation

Report two distinct numbers:

1. **Verified delivery %** = number of ideas marked **Released** ÷ 49 × 100.
2. **Evidence coverage %** = number of ideas with acceptance criteria and evidence reviewed ÷ 49 × 100.

Do not report a single overall percentage until the canonical 49-idea list is reconciled. Do not count draft PRs as completed ideas. If an idea spans multiple PRs, assess the combined result once, and avoid double-counting duplicate or stacked PRs.

## Current repository snapshot

The repository has a large open-PR queue. The audit PR #78 recorded 42 open PRs, 34 drafts and 6 PRs targeting non-`main` bases at the time of that snapshot. Those counts describe the queue, not completion.

### Known in-flight ideas and integration groups

| Idea / scope | Evidence visible in GitHub | Current assessment | Release blockers / next evidence |
|---|---|---|---|
| Ideas 09–13: interviews, scorecards, assessments, offers, recruitment documents | Draft PR #71 integrates the group; individual PRs #64–#67 also exist | In progress; integration not accepted | Run full backend tests, frontend typecheck/build, migration ordering/RLS review, tenant/role tests and authenticated browser acceptance. Resolve stacked-branch dependency. |
| Idea 04: application pipeline stages | Draft PRs #69 and #70 overlap; audit #78 flags duplication | Blocked pending consolidation | Compare diffs and tests; choose one canonical implementation, close/rebase duplicate only after evidence and explicit review. |
| Idea 05: application forms and candidate self-service | Draft PR #62 | In progress | Secure CV upload, staging migration verification, accessibility, tenant isolation and abuse tests. |
| Idea 13: recruitment documents and e-signatures | Draft PR #67 | In progress | Native provider webhook verification, rendering/workspace UI, secure link lifecycle, full checks and provider review. |
| Ideas 14–15: communication hub and notification preferences | Draft PR #68 | In progress | Provider sending/retries/webhooks and notification event production are not enabled; test, RLS and browser acceptance remain. |
| Idea 16: candidate portal/self-service dependency | PR #68 describes dependency on PR #62; canonical standalone scope still to reconcile | Unassessed / dependency-sensitive | Confirm canonical idea definition and verify identity, recovery, session revocation and candidate-safe APIs. |
| Idea 17: existing draft implementation | PR #68 points to PR #58 | Unassessed / dependency-sensitive | Reconcile PR #58 with canonical roadmap and test on its dependency branch. |
| Ideas 18–21: search, talent pools, imports and campaigns | Draft PR #72 | In progress; staging checks reported, not released | Per-record ACL integration, asynchronous/import security gaps, attribution, alerts, full API and browser acceptance; Vercel rate-limit failure noted in PR. |
| Ideas 22–27: organisation/workspaces, roles, agency client portal, collaboration, careers builder, job distribution | Draft audit PR #73; audit-only branch | Audit/planning documented; feature implementation not evidenced by PR #73 | Implement and test permission matrix, hiring-manager job scope, client submission grants/revocation, collaboration permissions, publication controls and provider lifecycle in dependency order. |
| Section 6: recruitment analytics/KPI dashboard (Idea 28) | User feature brief in project conversation; repository acceptance evidence not reconciled here | Unassessed | Validate metric definitions, query correctness, tenant isolation and dashboard acceptance against canonical scope. |
| Section 7: AI and responsible automation (Idea 34) | Draft PR #76 | In progress; staging schema and CI checks reported in PR | Cross-tenant/RLS and role tests, real evaluation suite, trusted retention scheduler, privacy/provider review and authenticated browser/accessibility QA. Vercel preview unavailable due to reported rate limit. |
| Section 8: privacy, consent and data rights (Idea 40) | Draft PR #77 | In progress; foundation only | Retention execution and deletion propagation, rights request orchestration, session revocation/MFA/step-up, provider secrets/webhooks/retries, backup monitoring/restore drills, migration/test verification. |
| Ideas 01–03 and remaining ideas not listed above | No complete canonical list/acceptance matrix reconciled in this snapshot | Unassessed | Find and pin the source roadmap, then add one row per idea with exact title, acceptance criteria, branch/PR, migration, CI, staging, production commit and evidence links. |

> This table is an initial triage, not a complete 49-row scorecard. Idea names are included only where they are supported by current repository/project evidence. Do not infer missing titles or statuses.

## Required fields for the canonical 49-row register

For every idea, maintain:

- Idea number and exact canonical title
- Section and acceptance criteria (link to source)
- Implementation PR(s) and canonical branch
- Duplicate/stacked PR dependencies
- Changed backend/frontend files
- Migration files and environment applied (none / local / staging / production)
- Automated test, typecheck and build result, with run URL and commit SHA
- Tenant isolation / role / RLS verification
- Authenticated UI and accessibility acceptance
- Deployment URL, environment and verified deployed commit SHA
- Known gaps, owner/next action and date last checked
- Status and evidence links

## Immediate execution order

1. Locate and reconcile the authoritative 49-idea roadmap; do not fabricate missing titles.
2. Snapshot current `main`, all open PRs and dependency relationships; consolidate duplicates and agree merge order.
3. Verify CI and staging evidence at each exact PR head commit.
4. Prioritise tenant isolation, role/permission enforcement and data-protection controls before broad release.
5. Release in small, dependency-ordered batches only after acceptance; do not merge or deploy production based on draft status or a preview badge alone.

## Initial completion reporting

- **Verified delivery percentage:** Not yet verified.
- **Evidence coverage percentage:** Not yet calculated; the canonical 49-row register is incomplete.
- **Production release claims:** Must be independently checked against the current deployed commit and runtime before marking any idea Released.


## Roadmap source reconciliation — first pass

A project Library source titled **Pasted markdown.md** contains detailed feature briefs for Ideas 04–08. This is source evidence for the idea titles and requirements below; it is not proof that the requirements have been implemented.

| Idea | Canonical title from source | Main acceptance themes from source | Evidence-based repository status |
|---|---|---|---|
| 04 | Applications & Recruitment Pipeline | Candidate/application separation; controlled stage transitions; audit history; tenant isolation; safe bulk actions; candidate-facing status separated from internal data | Draft PRs #69 and #70 overlap; consolidation and full acceptance tests still required |
| 05 | Application Forms & Candidate Self-Service | Versioned forms; server-side validation; candidate review before submission; private uploads; accessible mobile flow; privacy notice separate from marketing permission | Draft PR #62; secure CV upload, staging migration verification, accessibility and abuse tests remain |
| 06 | CV Parsing & Document Intelligence | Preserve originals; recruiter correction of extraction; confidence/provenance; duplicate detection; safe retries; logged access/processing | Exact repository implementation and acceptance evidence not reconciled in this pass |
| 07 | Candidate Matching & Job Fit Intelligence | Evidence-linked explanations; missing data not treated as negative; auditable criteria/scoring; recruiter override with reason; quality and fairness evaluation | Exact repository implementation and acceptance evidence not reconciled in this pass |
| 08 | Recruitment Workflow Automation | Draft/test/publish/disable lifecycle; traceable runs; idempotent retries; runtime permission checks; recovery; logged communications | Draft PR #63 describes a workflow foundation, not a complete execution engine; event producers, workers, execution-time permissions, idempotent side effects and recovery remain |

**Source limitation:** The retrieved source segment contains Ideas 04–08 only. It does not by itself establish the complete authoritative list of all 49 ideas. The remaining titles must be retrieved from the source material before this register can be considered canonical.

## Updated progress snapshot — 2026-10-22

- **Tracker task completion:** 100% for the initial tracker creation; further reconciliation is still in progress.
- **Roadmap title coverage:** 5 of 49 titles have now been confirmed against the source segment (10.2%). This is title coverage only, not implementation completion.
- **Verified product delivery:** Not yet calculable; the canonical 49-row acceptance register and production deployment evidence are incomplete.
- **Pending:** Retrieve the remaining source sections; map each idea to main/PRs/migrations/tests; verify current deployed commit; then calculate verified delivery and evidence coverage.

## Evidence refresh — 2026-10-26

This is a dated evidence snapshot, not a product-completion percentage. CI evidence below is tied to the exact recorded head commit.

| Workstream | PR / commit checked | Automated evidence | Remaining acceptance |
|---|---|---|---|
| Candidate deletion guard | [PR #83](https://github.com/venugopalc80/ATS/pull/83), `9105c039e130f0adfe4d7bb16b5157e5e536205d` | [Run 40145143247](https://github.com/venugopalc80/ATS/actions/runs/40145143247) passed backend unit tests, frontend typecheck and production build | Staging schema parity; authenticated linked-record deletion tests; review archive/restore and role controls |
| Section 6 analytics | [PR #80](https://github.com/venugopalc80/ATS/pull/80), `4b381fc3c785c7b18463d066f892ae53c9ab3109` | [Run 40312149553](https://github.com/venugopalc80/ATS/actions/runs/40312149553) passed backend unit tests, frontend typecheck and production build | Metric/tenant/export acceptance against current staging; browser acceptance and deployed preview verification |
| Section 9 commercial operations | [PR #81](https://github.com/venugopalc80/ATS/pull/81), `13b1ba417c67820e9b127e31db6af48aa912b0ed` | [Run 40312283758](https://github.com/venugopalc80/ATS/actions/runs/40312283758) passed billing-focused unit checks, frontend typecheck and production build; [run 40312283887](https://github.com/venugopalc80/ATS/actions/runs/40312283887) also passed generic backend/frontend checks | Entitlement enforcement across actual recruitment operations; Stripe test checkout/webhooks end to end; tenant isolation and support-grant expiry/revocation |

### Newly identified migration risk

On the checked-in `main` branch, both `supabase/migrations/013_candidate_documents.sql` and `supabase/migrations/20261012090000_candidate_documents.sql` use `CREATE TABLE IF NOT EXISTS public.candidate_documents`, but define different constraints/indexes. With `IF NOT EXISTS`, the later file does not reconcile an already-created table. The effective staging schema and migration ledger therefore need inspection before treating document retention/deletion safeguards as accepted. Do not rewrite an applied migration in place; use a reviewed forward migration if the actual schema needs correction.

### Status rules reaffirmed

- These CI runs are code-level evidence only; they do not establish staging acceptance or a production release.
- PRs #80, #81 and #83 remain drafts; no production change is implied by this snapshot.
- Overall verified delivery and evidence coverage percentages remain **not yet verified** until the canonical 49-idea register and release evidence are reconciled.

### Read-only staging schema check — 2026-10-26

ATS-Staging project `riauyrhfnlsxmtgipuxi` was inspected read-only. No SQL writes or migrations were run.

- The staging migration ledger lists `013_candidate_documents`; it does not list `20261012090000_candidate_documents` as a migration name.
- The live `public.candidate_documents` table exists and its `candidate_id` FK uses `ON DELETE CASCADE`.
- The live table has a SHA-256 format check, `candidate_documents_org_sha256_idx`, and `candidate_documents_search_org_created_idx`, which are not all represented in `013_candidate_documents.sql`.
- The live `uploaded_by` column has no foreign-key constraint.
- These observations indicate that the live schema and the checked-in candidate-document migration files do not map cleanly by migration name alone. The exact source of each live constraint/index must be reconciled against the full migration history before changing the schema.
- The candidate deletion guard's table reference is valid in staging, but this does not replace authenticated application-level acceptance tests or verify the full deployed application.

**Next action:** compare the staging ledger and checked-in migration history, establish the intended canonical candidate-document schema, then prepare a reviewed forward migration only if required. Never rewrite an already-applied migration in place.
