-- Assertions run after the hardening migration in an isolated PostgreSQL database.
DO $$
DECLARE expected text[] := ARRAY[
  'applications_member_all','audit_member_read','candidates_member_all','clients_member_all',
  'interviews_member_all','job_distribution_member_read','job_distribution_member_write',
  'jobs_member_all','memberships_member_read','organizations_member_read','offers_member_all',
  'placements_member_all','profiles_self_read','application_stage_history_member_insert',
  'application_stage_history_member_read'
];
DECLARE missing_count integer;
DECLARE trigger_function text;
BEGIN
  SELECT count(*) INTO missing_count
  FROM unnest(expected) AS e(policy_name)
  WHERE NOT EXISTS (
    SELECT 1 FROM pg_policies p
    WHERE p.schemaname = 'public'
      AND p.policyname = e.policy_name
      AND p.roles = ARRAY['authenticated']::name[]
  );
  IF missing_count <> 0 THEN
    RAISE EXCEPTION '% policies are missing or not authenticated-only', missing_count;
  END IF;

  IF has_function_privilege('anon', 'public.is_org_member(uuid)', 'EXECUTE') THEN
    RAISE EXCEPTION 'anon can still execute is_org_member(uuid)';
  END IF;
  IF NOT has_function_privilege('authenticated', 'public.is_org_member(uuid)', 'EXECUTE') THEN
    RAISE EXCEPTION 'authenticated cannot execute is_org_member(uuid)';
  END IF;

  FOREACH trigger_function IN ARRAY ARRAY[
    'public.audit_workflow_status_change()',
    'public.capture_record_change()',
    'public.rls_auto_enable()'
  ] LOOP
    IF has_function_privilege('anon', trigger_function, 'EXECUTE')
       OR has_function_privilege('authenticated', trigger_function, 'EXECUTE') THEN
      RAISE EXCEPTION 'Browser role retains EXECUTE on %', trigger_function;
    END IF;
    IF EXISTS (
      SELECT 1
      FROM pg_proc p
      CROSS JOIN LATERAL aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a
      WHERE p.oid = trigger_function::regprocedure
        AND a.grantee = 0
        AND a.privilege_type = 'EXECUTE'
    ) THEN
      RAISE EXCEPTION 'PUBLIC retains EXECUTE on %', trigger_function;
    END IF;
  END LOOP;

  IF has_function_privilege('anon', 'public.is_org_member(uuid)', 'EXECUTE') THEN
    RAISE EXCEPTION 'anon still has helper EXECUTE';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM pg_proc p
    CROSS JOIN LATERAL aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a
    WHERE p.oid = 'public.is_org_member(uuid)'::regprocedure
      AND a.grantee = 0
      AND a.privilege_type = 'EXECUTE'
  ) THEN
    RAISE EXCEPTION 'PUBLIC retains helper EXECUTE';
  END IF;
END
$$;

-- The event trigger must still work after its function's direct EXECUTE grant is revoked.
CREATE TABLE public.rls_enabled_by_event_trigger (id integer);
DO $$
BEGIN
  IF NOT (SELECT c.relrowsecurity FROM pg_class c WHERE c.oid = 'public.rls_enabled_by_event_trigger'::regclass) THEN
    RAISE EXCEPTION 'rls_auto_enable event trigger did not enable RLS';
  END IF;
END
$$;

-- Signed-in application writes must still invoke both SECURITY DEFINER row triggers.
SET ROLE authenticated;
INSERT INTO public.applications(id, organization_id, status)
VALUES ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000010', 'new');
UPDATE public.applications SET status = 'screening'
WHERE id = '00000000-0000-0000-0000-000000000001';
RESET ROLE;

DO $$
BEGIN
  IF (SELECT count(*) FROM public.audit_events) < 3 THEN
    RAISE EXCEPTION 'Expected row-history and workflow-status triggers to record changes';
  END IF;
END
$$;
