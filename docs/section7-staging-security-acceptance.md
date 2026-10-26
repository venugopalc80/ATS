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
