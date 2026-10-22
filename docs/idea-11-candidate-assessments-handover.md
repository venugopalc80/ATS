# AQERITH Idea 11 — Candidate Assessments & Skills Testing

## Scope implemented on this branch

- Adds assessment templates tied to a job optionally, with assessment type, candidate instructions, evaluation guidance, role requirements, accessibility options and external-provider key.
- Adds application-linked assignments with deadline, extension reason, accommodation arrangement fields, status and an instruction snapshot.
- Adds submissions, sourced results, human reviews, assignment event history and provider webhook replay ledger.
- Adds authenticated FastAPI routes for template creation/edit/publish, assignment/list/update/start, submission, result entry, human review and evidence retrieval.
- Adds a recruiter-facing Next.js assessment workspace.
- Adds schema validation and provider-signature tests.

## Security and fairness controls

- API operations check membership in the specified organisation; management operations require owner/admin/recruiter/hiring-manager roles.
- Foreign keys include organisation scope for application/template/submission/result relationships.
- RLS is enabled and browser writes are revoked; mutations go through the authenticated API.
- Provider webhooks use per-provider HMAC SHA-256 secrets, constant-time signature comparison, payload hashes and provider-event deduplication.
- Provider events update assessment records only. They do not mutate application stages or make hiring decisions.
- Results store source and methodology. Human review remains explicit.
- Deadline extensions require a later timestamp and a reason, and write assignment/audit events.
- Accommodation records are limited to practical arrangements; avoid recording diagnoses or unrelated sensitive information.
- Assessment templates cannot be published without at least one role requirement.

## Migration

supabase/migrations/20261022124500_candidate_assessments.sql

Applied successfully to ATS-Staging on 2026-10-22. Post-apply verification confirmed all seven assessment tables, RLS enabled on each, the append-only assignment-event trigger present, and no grants to anon/authenticated. Production was not changed.

## Provider configuration

Configure a distinct secret per provider using ASSESSMENT_PROVIDER_<PROVIDER_KEY_NORMALIZED>_WEBHOOK_SECRET. Sign the exact raw request body as sha256=<hex HMAC-SHA256>, and send a unique X-Assessment-Event-Id.

## Known limitations / release blockers

- Candidate-facing self-service delivery/authentication is not implemented in this first pass. The submission endpoint currently requires an authenticated organisation member, so it is not yet a candidate portal.
- File-upload/storage integration for large work samples is not implemented; the current submission API supports bounded text evidence or an external provider reference.
- The generic provider webhook is an adapter contract, not a verified integration with a named vendor.
- Accessibility arrangements are recorded but no automated alternative-format or extended-time delivery mechanism exists yet.
- Browser build, backend test suite, staging migration application and authenticated preview verification must pass before acceptance. Do not merge or deploy until these checks are complete.

## Acceptance checklist

- [x] Assessment templates include type, instructions, role requirements and accessibility options.
- [x] Assignment records are application-scoped and snapshot the instructions.
- [x] Deadlines and extensions are stored and audited.
- [x] Result source and methodology are required.
- [x] Recruiters can retrieve submissions, results and reviews together.
- [x] Human review is explicit and does not automatically change application status.
- [x] Provider webhook signature verification and replay deduplication are implemented in code.
- [ ] Candidate-facing submission and accessibility journey verified.
- [ ] Private work-sample upload and retention path verified.
- [x] Migration applied and schema verified in ATS-Staging.
- [ ] Backend tests and frontend typecheck/build pass in CI. GitHub Actions workflow runs were not reported; Vercel preview checks failed due to the team's build-rate limit, so no build result is available.
- [ ] Authenticated preview tested across tenant and permission boundaries.
- [ ] Production release checks completed.
