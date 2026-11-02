-- Restrict direct Data API reads of candidate communications to members
-- whose effective role/individual access includes candidates.communicate.
drop policy if exists candidate_communications_member_read on public.candidate_communications;
create policy candidate_communications_permission_read
on public.candidate_communications
for select to authenticated
using (
  exists (
    select 1
    from public.organization_members m
    left join public.organization_roles role_template
      on role_template.organization_id = m.organization_id
     and (
       (m.custom_role_id is not null and role_template.id = m.custom_role_id)
       or (m.custom_role_id is null and role_template.role_key = m.role)
     )
    left join public.organization_role_permissions role_permission
      on role_permission.organization_id = m.organization_id
     and role_permission.role_id = role_template.id
     and role_permission.permission_key = 'candidates.communicate'
    left join public.organization_member_permission_overrides member_override
      on member_override.organization_id = m.organization_id
     and member_override.user_id = m.user_id
     and member_override.permission_key = 'candidates.communicate'
     and (member_override.expires_at is null or member_override.expires_at > now())
    where m.organization_id = candidate_communications.organization_id
      and m.user_id = auth.uid()
      and case
        when m.role = 'owner' then true
        when member_override.effect is not null then member_override.effect = 'allow'
        else coalesce(role_permission.allowed, false)
      end
  )
);
