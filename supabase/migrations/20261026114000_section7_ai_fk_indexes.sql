-- Section 7: index foreign-key columns used for joins and referential checks.
-- Organisation-leading indexes already exist on the tenant-scoped tables where applicable.
create index if not exists ai_use_cases_owner_user_idx
  on public.ai_use_cases (owner_user_id);

create index if not exists ai_model_versions_created_by_idx
  on public.ai_model_versions (created_by);
create index if not exists ai_model_versions_approved_by_idx
  on public.ai_model_versions (approved_by);

create index if not exists ai_runs_use_case_idx
  on public.ai_runs (use_case_id);
create index if not exists ai_runs_model_version_idx
  on public.ai_runs (model_version_id);
create index if not exists ai_runs_actor_user_idx
  on public.ai_runs (actor_user_id);

create index if not exists ai_recommendations_ai_run_idx
  on public.ai_recommendations (ai_run_id);
create index if not exists ai_recommendations_model_version_idx
  on public.ai_recommendations (model_version_id);
create index if not exists ai_recommendations_reviewed_by_idx
  on public.ai_recommendations (human_reviewed_by);

create index if not exists ai_jd_versions_ai_run_idx
  on public.ai_job_description_versions (ai_run_id);
create index if not exists ai_jd_versions_created_by_idx
  on public.ai_job_description_versions (created_by);
create index if not exists ai_jd_versions_reviewed_by_idx
  on public.ai_job_description_versions (reviewed_by);
create index if not exists ai_jd_versions_published_by_idx
  on public.ai_job_description_versions (published_by);

create index if not exists ai_interview_kits_ai_run_idx
  on public.ai_interview_kits (ai_run_id);
create index if not exists ai_interview_kits_created_by_idx
  on public.ai_interview_kits (created_by);
create index if not exists ai_interview_kits_reviewed_by_idx
  on public.ai_interview_kits (reviewed_by);

create index if not exists ai_evaluation_runs_model_version_idx
  on public.ai_evaluation_runs (model_version_id);
create index if not exists ai_evaluation_runs_started_by_idx
  on public.ai_evaluation_runs (started_by);

create index if not exists ai_evaluation_results_org_idx
  on public.ai_evaluation_results (organization_id);
create index if not exists ai_evaluation_results_run_idx
  on public.ai_evaluation_results (evaluation_run_id);

create index if not exists ai_fairness_audits_org_idx
  on public.ai_fairness_audits (organization_id);
create index if not exists ai_fairness_audits_reviewed_by_idx
  on public.ai_fairness_audits (reviewed_by);

create index if not exists ai_incidents_ai_run_idx
  on public.ai_incidents (ai_run_id);
create index if not exists ai_incidents_model_version_idx
  on public.ai_incidents (model_version_id);
create index if not exists ai_incidents_reported_by_idx
  on public.ai_incidents (reported_by);
create index if not exists ai_incidents_assigned_to_idx
  on public.ai_incidents (assigned_to);
