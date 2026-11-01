-- Restrict tenant-table policies to authenticated sessions and remove direct
-- browser execution from trigger-only SECURITY DEFINER helpers.
--
-- This migration changes grants and policy role targets only. It does not
-- modify recruitment records. The policy list is based on the live ATS schema
-- inspected on 2026-11-01; optional stage-history policies are included when
-- that table exists (ATS-Staging has it, production currently does not).
--
-- Keep this migration separate from the granular-permissions rollout. The
-- API-level permission checks remain the primary control for recruiter roles.

begin;

revoke execute on function public.audit_workflow_status_change()
  from public, anon, authenticated;
revoke execute on function public.capture_record_change()
  from public, anon, authenticated;
revoke execute on function public.rls_auto_enable()
  from public, anon, authenticated;

-- RLS membership policies need this helper for signed-in sessions. Anonymous
-- callers and PUBLIC must not be able to invoke it.
revoke execute on function public.is_org_member(uuid) from public, anon;
grant execute on function public.is_org_member(uuid) to authenticated;

do $$
declare
  policy_row record;
  required_policies constant text[][] := array[
    array['applications', 'applications_member_all'],
    array['audit_events', 'audit_member_read'],
    array['candidates', 'candidates_member_all'],
    array['clients', 'clients_member_all'],
    array['interviews', 'interviews_member_all'],
    array['job_distribution_channels', 'job_distribution_member_read'],
    array['job_distribution_channels', 'job_distribution_member_write'],
    array['jobs', 'jobs_member_all'],
    array['organization_members', 'memberships_member_read'],
    array['organizations', 'organizations_member_read'],
    array['offers', 'offers_member_all'],
    array['placements', 'placements_member_all'],
    array['profiles', 'profiles_self_read']
  ];
begin
  foreach policy_row slice 1 in array required_policies loop
    if not exists (
      select 1
      from pg_policies
      where schemaname = 'public'
        and tablename = policy_row[1]
        and policyname = policy_row[2]
    ) then
      raise exception 'Expected policy public.%.% is missing; stop and reconcile schema before applying security hardening',
        policy_row[1], policy_row[2];
    end if;

    execute format(
      'alter policy %I on public.%I to authenticated',
      policy_row[2],
      policy_row[1]
    );
  end loop;

  -- This feature exists in ATS-Staging but is absent from the current
  -- production schema. Apply the same role restriction when present.
  if to_regclass('public.application_stage_history') is not null then
    for policy_row in
      select policyname
      from pg_policies
      where schemaname = 'public'
        and tablename = 'application_stage_history'
        and policyname in (
          'application_stage_history_member_insert',
          'application_stage_history_member_read'
        )
    loop
      execute format(
        'alter policy %I on public.application_stage_history to authenticated',
        policy_row.policyname
      );
    end loop;
  end if;
end
$$;

commit;
