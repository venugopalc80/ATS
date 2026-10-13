-- Dashboard and tenant-query indexes recovered from the production catalog.
CREATE INDEX IF NOT EXISTS applications_human_reviewed_by_idx ON public.applications (human_reviewed_by);
CREATE INDEX IF NOT EXISTS audit_events_actor_user_idx ON public.audit_events (actor_user_id);
CREATE INDEX IF NOT EXISTS clients_organization_idx ON public.clients (organization_id);
CREATE INDEX IF NOT EXISTS clients_organization_name_idx ON public.clients (organization_id, name);
CREATE INDEX IF NOT EXISTS clients_organization_status_idx ON public.clients (organization_id, status);
CREATE INDEX IF NOT EXISTS jobs_created_by_idx ON public.jobs (created_by);
CREATE INDEX IF NOT EXISTS jobs_hiring_manager_idx ON public.jobs (hiring_manager_id);
CREATE INDEX IF NOT EXISTS jobs_organization_client_idx ON public.jobs (organization_id, client_id);
CREATE INDEX IF NOT EXISTS jobs_organization_status_idx ON public.jobs (organization_id, status);
CREATE INDEX IF NOT EXISTS jobs_recruiter_idx ON public.jobs (recruiter_id);
CREATE INDEX IF NOT EXISTS organization_members_user_idx ON public.organization_members (user_id);
