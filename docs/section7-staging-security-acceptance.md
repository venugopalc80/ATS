# Section 7 staging security acceptance notes

Date checked: 2026-10-26
Project: ATS-Staging (`riauyrhfnlsxmtgipuxi`)
Scope: Section 7 AI governance tables only. This is a read-only inspection report, not a penetration-test certification.

## Table-level checks

- Found 10 `public.ai_*` tables.
- RLS is enabled on all 10 tables.
- Each table has a SELECT policy.
- `anon` has no direct table grants on these AI tables.
- `authenticated` has SELECT only; no direct INSERT, UPDATE, or DELETE grants were found.
- Policy intent:
  - `ai_runs`, `ai_use_cases`, `ai_recommendations`, `ai_interview_kits`, and `ai_job_description_versions`: organisation-member read.
  - `ai_model_versions`, `ai_evaluation_runs`, `ai_evaluation_results`, `ai_fairness_audits`, and `ai_incidents`: owner/admin read.
- Member policies resolve organisation membership using `auth.uid()`; admin policies explicitly match membership and role in (`owner`, `admin`).

## Items requiring further verification

1. These checks inspect grants and policy definitions; they do not yet exercise authenticated requests with two real staging identities from different organisations. Cross-tenant runtime tests remain pending.
2. The shared `public.is_org_member(uuid)` helper is a SECURITY DEFINER function executable by authenticated users and is used by organisation-member RLS policies. Its current body returns only whether the caller identified by `auth.uid()` belongs to the supplied organisation. Supabase Security Advisor flags callable SECURITY DEFINER functions in exposed schemas. Do not change this shared helper casually: it may support policies outside Section 7. Review whether it should be moved to a non-exposed schema and update dependent policies in a separately scoped migration.
3. The project Security Advisor also reports unrelated existing findings: tables with RLS but no policies, `vector` extension in `public`, leaked-password protection disabled, and other project-wide performance warnings. They are not introduced by Section 7 and were not changed in this task.

## Release conclusion

Section 7 table grants and policy definitions match the intended read-only direct Data API surface. This is a partial acceptance result, not proof of full tenant isolation. Continue with runtime two-tenant RLS tests, API role checks, provider-backed AI evaluations, retention scheduling, and browser QA before promoting the draft PR.

## Additional checks on 2026-10-31

- Added API regression coverage proving a non-member cannot invoke the AI assistant using another organisation ID; the membership denial must happen before role lookup, database access or provider invocation.
- Added API regression coverage proving a non-member cannot submit feedback against an AI run in another organisation; membership denial must happen before database access.
- In staging, simulated the existing owner identity through the JWT subject claim and evaluated the shared membership helper. It returned `true` for the owner's existing organisation and `false` for an unrelated UUID. This is a helper-level check only; it does not replace a live Data API/RLS test with two separate authenticated users and tenant-owned rows.
- Latest tenant-boundary tests were committed on the feature branch. Their CI result must be confirmed before treating them as passing.

- Latest Section 7 CI run `41200340008` completed successfully on the tenant-boundary code change: backend compilation, backend unit tests and frontend type-check all passed. The following docs-only commit also has a successful Section 7 workflow run.
- The same code commit's Vercel checks failed because the team build-rate limit was reached (`upgradeToPro=build-rate-limit`); this is not a reported application build error. No billing change was made.
- A dependency scan of staging RLS policies found that `public.is_org_member(uuid)` is used by many existing non-AI policies as well as five Section 7 member-read policies. This confirms it is a shared, project-wide authorization helper. Its ACL currently grants EXECUTE to `authenticated` and `service_role`, not `anon` or `PUBLIC`; its body checks membership against `auth.uid()`. Do not relocate or replace it as part of this Section 7 change without a separate migration plan and regression coverage for all dependent policies.
- Quantified the shared-helper blast radius in staging: `public.is_org_member(uuid)` appears in 50 RLS policies across 43 public tables. This reinforces that changing its schema/name/privileges is a separate platform-wide security migration, not a safe local Section 7 patch.
