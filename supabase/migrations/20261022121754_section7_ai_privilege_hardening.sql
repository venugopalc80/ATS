-- Remove inherited default table privileges from browser roles.
-- AI writes are API-only; RLS-scoped reads are granted only to authenticated users.
revoke all privileges on public.ai_use_cases, public.ai_model_versions, public.ai_runs,
 public.ai_recommendations, public.ai_job_description_versions, public.ai_interview_kits,
 public.ai_evaluation_runs, public.ai_evaluation_results, public.ai_fairness_audits, public.ai_incidents
 from anon, authenticated;

grant select on public.ai_use_cases, public.ai_runs, public.ai_recommendations,
 public.ai_job_description_versions, public.ai_interview_kits to authenticated;
grant select on public.ai_model_versions, public.ai_evaluation_runs, public.ai_evaluation_results,
 public.ai_fairness_audits, public.ai_incidents to authenticated;
