-- Query indexes for database-backed Section 4 search filters.
-- Keep initial search on indexed structured fields and skill arrays; add full-text/trigram only after profiling.
create index if not exists candidates_search_org_status_created_idx
  on public.candidates (organization_id, status, created_at desc);
create index if not exists candidates_search_org_experience_idx
  on public.candidates (organization_id, years_experience)
  where years_experience is not null;
create index if not exists candidates_search_org_location_idx
  on public.candidates (organization_id, country_code, city);
create index if not exists candidates_skills_gin_idx
  on public.candidates using gin (skills);

create index if not exists applications_search_org_status_created_idx
  on public.applications (organization_id, status, created_at desc);
create index if not exists applications_search_org_source_idx
  on public.applications (organization_id, source, created_at desc);

create index if not exists jobs_search_org_status_created_idx
  on public.jobs (organization_id, status, created_at desc);
create index if not exists jobs_search_org_recruiter_idx
  on public.jobs (organization_id, recruiter_id, status);
create index if not exists jobs_required_skills_gin_idx
  on public.jobs using gin (required_skills);

create index if not exists candidate_documents_search_org_created_idx
  on public.candidate_documents (organization_id, created_at desc)
  where deleted_at is null;
