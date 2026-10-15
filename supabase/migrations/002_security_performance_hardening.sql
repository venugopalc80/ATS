-- Security hardening for the core tenant tables.
-- SECURITY DEFINER membership helper is callable only by authenticated users;
-- the helper is required by authenticated RLS policies.
CREATE OR REPLACE FUNCTION public.is_org_member(target_org uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.organization_members m
    WHERE m.organization_id = target_org AND m.user_id = auth.uid()
  );
$$;

REVOKE EXECUTE ON FUNCTION public.is_org_member(uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.is_org_member(uuid) TO authenticated;

ALTER POLICY organizations_member_read ON public.organizations TO authenticated;
ALTER POLICY profiles_self_read ON public.profiles TO authenticated;
ALTER POLICY memberships_member_read ON public.organization_members TO authenticated;
ALTER POLICY clients_member_all ON public.clients TO authenticated;
ALTER POLICY jobs_member_all ON public.jobs TO authenticated;
ALTER POLICY candidates_member_all ON public.candidates TO authenticated;
ALTER POLICY applications_member_all ON public.applications TO authenticated;
ALTER POLICY audit_member_read ON public.audit_events TO authenticated;
