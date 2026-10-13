-- Restrict SECURITY DEFINER helpers to the roles that need them.
-- Trigger functions are invoked by PostgreSQL triggers; clients do not need direct EXECUTE.
REVOKE EXECUTE ON FUNCTION public.audit_workflow_status_change() FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.capture_record_change() FROM PUBLIC, anon, authenticated;
DO $$
BEGIN
  IF to_regprocedure('public.rls_auto_enable()') IS NOT NULL THEN
    EXECUTE 'REVOKE EXECUTE ON FUNCTION public.rls_auto_enable() FROM PUBLIC, anon, authenticated';
  END IF;
END $$;

-- RLS policies need this helper for authenticated membership checks, but anon/PUBLIC do not.
REVOKE EXECUTE ON FUNCTION public.is_org_member(uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.is_org_member(uuid) TO authenticated;

ALTER POLICY applications_member_all ON public.applications TO authenticated;
ALTER POLICY audit_member_read ON public.audit_events TO authenticated;
ALTER POLICY candidates_member_all ON public.candidates TO authenticated;
ALTER POLICY clients_member_all ON public.clients TO authenticated;
ALTER POLICY interviews_member_all ON public.interviews TO authenticated;
ALTER POLICY job_distribution_member_read ON public.job_distribution_channels TO authenticated;
ALTER POLICY job_distribution_member_write ON public.job_distribution_channels TO authenticated;
ALTER POLICY jobs_member_all ON public.jobs TO authenticated;
ALTER POLICY memberships_member_read ON public.organization_members TO authenticated;
ALTER POLICY organizations_member_read ON public.organizations TO authenticated;
ALTER POLICY offers_member_all ON public.offers TO authenticated;
ALTER POLICY placements_member_all ON public.placements TO authenticated;
