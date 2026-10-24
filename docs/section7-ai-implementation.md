# AQERITH Section 7 — Responsible AI implementation

Branch: `feat/section7-responsible-ai`  
Pull request: https://github.com/venugopalc80/ATS/pull/76  
Status: implementation in review; not merged or deployed.

## Implemented in this branch

- Additive PostgreSQL migration for organisation-scoped AI use cases, model versions, AI run metadata, recommendation evidence/reviews, versioned job-description drafts, versioned interview kits, evaluation runs/results, aggregate fairness audits and AI incidents.
- Backend AI provider adapter with a server-side approval gate, bounded HTTP timeouts, response validation and a system prompt that treats retrieved CVs, emails, job descriptions and user-provided text as untrusted data.
- Permission-checked FastAPI endpoints for AI generation, governance configuration, model registration/approval, evaluation recording, fairness audit records, incident reporting/remediation, feedback, recommendation review, job-description review/publication and interview-kit review.
- AI run history stores source record references and an input fingerprint rather than copying full raw prompts into the run record. Generated output has a configurable expiry timestamp.
- Job-description drafts remain in a versioned draft table until a permitted user reviews and publishes them. Interview kits are versioned and require human review.
- Recruiter-facing `/ai` workspace with evidence references, feedback/report controls and admin governance forms.
- Unit tests for prompt injection guardrails, stable fingerprints, provider approval/credentials, API route import and request validation.
- GitHub Actions checks for Python compile, backend tests and frontend TypeScript checks.

## Provider enablement gates

AI generation is intentionally unavailable unless all gates pass:

1. Set server-side `AI_PROVIDER_APPROVED=true` only after vendor, privacy, security, transfer, retention and contractual reviews are complete.
2. Set `AI_PROVIDER_NAME` to the exact provider identifier recorded in the model registry (defaults to `openai-compatible`). The registered provider must match this server-side value.\n3. Set `AI_PROVIDER_API_KEY` as a server-only secret. Do not expose it through a `NEXT_PUBLIC_*` variable.
4. Set `AI_PROVIDER_BASE_URL` only to the approved OpenAI-compatible provider endpoint (defaults to the OpenAI API endpoint).
5. An organisation administrator must configure the use case as enabled and approved, with provider approval recorded.
6. An organisation administrator must register the exact model/version and mark data processing approved.
7. Run and pass a documented evaluation suite for that model version, then explicitly approve the model through the governance endpoint.
8. Verify that the configured provider's retention, training, residency, subprocessor and deletion controls match the applicable data-processing approval.

Do not send real candidate data to an external provider before these gates have been reviewed and enabled.

## Retention and privacy

- The default AI-run retention period is 90 days, configurable per organisation use case from 1 to 3,650 days.
- AI run records store references, hashes, output, feedback and expiry timestamps. Raw CV text is not copied into run history, but it may be included in the live provider request for a task that uses CV evidence.
- `POST /api/ai/governance/retention-cleanup?organization_id=...` deletes expired AI runs for the selected organisation and writes an aggregate cleanup audit event.
- The cleanup endpoint is administrator-only. **A production scheduler has not been configured in this PR.** Before production enablement, schedule this endpoint through a trusted server-side job, or implement an approved database/worker scheduler, and test missed runs and retries.
- Define and review retention separately for versioned job-description drafts, interview kits, incidents, evaluations and fairness audit records. The AI-run cleanup endpoint does not delete these records.
- Fairness audit records are for approved aggregate datasets only. Do not infer protected characteristics or upload individual-level sensitive audit data. Small or invalid sample sizes receive an explicit uncertainty note.

## Known limitations and required follow-up

- Evaluation results are currently submitted by an authorised administrator through the API; connect a representative, version-controlled test suite and release gate before approving production models.
- Fairness monitoring stores reviewed aggregate results and caveats; it does not itself establish fairness or prove absence of discrimination.
- Job-description quality findings require a reviewer to verify clarity, accessibility, exclusionary wording and every salary/benefit/qualification/work-arrangement claim before publication.
- Interview-kit output is stored as a draft payload and must be reviewed and structured by an authorised interviewer before use.
- The current AI workspace does not yet provide a full graphical workflow for every governance operation. API controls remain available for evaluation completion, incident remediation and retention cleanup.
- The backend uses a server-side database connection. API endpoints perform explicit membership/role and organisation-scoped record checks; continue to test these checks with users from two organisations. RLS remains defence in depth for browser-visible tables.
- The two migrations were applied to `ATS-Staging`. Verified all 10 AI tables exist with RLS enabled, the expected scoped SELECT policies exist, and browser roles have only explicit authenticated SELECT grants (no `anon` grants or browser write/TRUNCATE privileges). Functional cross-tenant/RLS request tests are still required. Production has not been migrated.

## Verification checklist

- [ ] GitHub Actions Python compile check passes on the latest PR head.
- [ ] Backend unit tests pass on the latest PR head.
- [ ] Frontend TypeScript check passes on the latest PR head.
- [x] Apply migrations to `ATS-Staging`; verify AI tables, RLS policies and browser grants.\n- [ ] Verify migration replay/upgrade behaviour from a clean disposable database.
- [ ] Verify cross-tenant reads/writes fail for all AI endpoints.
- [ ] Verify non-admins cannot configure use cases/models, inspect governance data, approve models, create fairness audits, remediate incidents or run retention cleanup.
- [ ] Verify a model cannot be approved without documented data-processing approval and a passing evaluation.
- [ ] Verify untrusted instructions embedded in a CV/email/job description cannot change permissions or trigger side effects.
- [ ] Verify external provider calls are blocked when any provider approval gate is absent.
- [ ] Verify unsupported facts are flagged and evidence references are shown in the UI.
- [ ] Verify human approval is required before publishing a job description or using an interview kit.
- [ ] Verify retention cleanup deletes only expired records in the selected organisation.
- [ ] Verify a staging/preview session in an authenticated browser before production release.


## Security verification work in progress (2026-10-22)

- Added regression tests for organisation-scoped evidence lookups for candidates, jobs, applications, interviews and recorded recommendations. Missing records outside the requested organisation must resolve to HTTP 404 and must not be sent to the provider.
- Added role-guard tests ensuring a viewer cannot run candidate summaries or generate interview questions.
- The latest verified Section 7 workflow for commit `e35571309e70afa9025271dbbce99127925c233c` passed backend dependency installation, Python compile, backend unit tests, frontend dependency installation and TypeScript typecheck. The tenant-isolation, role-guard and human-review audit tests were included in that successful run.
- A live staging catalogue query confirmed all ten Section 7 tables have RLS enabled and one explicit read policy each. The policies for member-readable records scope membership to the row's organisation; evaluation, fairness and incident tables are restricted to organisation owners/admins.
- The staging security advisor also reports broader existing findings outside this Section 7 migration: eight assessment/candidate-document tables have RLS but no policies; public.is_org_member(uuid) is a callable SECURITY DEFINER helper; the vector extension is in public; and leaked-password protection is disabled. These require a separate impact review before changing shared security primitives, because the membership helper is used by existing RLS policies.



## Human-review audit improvement (2026-10-22)

- Job-description and interview-kit review audit events now retain the review outcome and the reviewer's supplied override/send-back rationale.
- Added unit tests for both review endpoints to verify that the reason is persisted in audit-event metadata.
- The same verified Section 7 workflow passed the backend unit test suite, including both review-audit tests.



## Governance regression tests (2026-10-22)

- Added model-approval gate tests: a model cannot be approved without recorded data-processing approval, and cannot be approved without a passing evaluation run.
- Added a fairness-audit test verifying groups with fewer than 10 observations are flagged in uncertainty notes and audit metadata.
- The Section 7 workflow passed on commit `25fcc5060398b6fae2af0d23ce036291e64a9f33` (run #44: backend tests and frontend TypeScript checks succeeded), including model-approval gates and small-sample fairness warnings.
- Follow-up hardening validates evaluation pass criteria before recording results: `minimum_cases` must be a positive integer and `max_failure_rate` must be numeric and between 0 and 1. Invalid criteria return HTTP 409 before evaluation result rows are written.
- Added regression coverage for zero/invalid minimum case counts, out-of-range failure rates, booleans and non-numeric failure-rate values. The code/test commit is `809b5cdbb9c8812909b96fd38d23fffbde291a60`; its Section 7 Actions run #48 was still in progress at the time of this note, so this newest change remains unverified until that run completes.
