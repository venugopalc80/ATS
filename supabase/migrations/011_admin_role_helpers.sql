-- 011_admin_role_helpers.sql
-- Central database helpers for role checks; API routes must still enforce these
-- checks before privileged operations.
create or replace function public.current_user_org_role(target_org uuid)
returns text
language sql
stable
security definer
set search_path = public
as $$
  select m.role
  from public.organization_members m
  where m.organization_id = target_org
    and m.user_id = auth.uid()
  limit 1;
$$;

create or replace function public.is_org_admin(target_org uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.organization_members m
    where m.organization_id = target_org
      and m.user_id = auth.uid()
      and m.role in ('owner', 'admin')
  );
$$;

-- Audit rows are append-only for ordinary authenticated clients.
drop policy if exists audit_member_read on public.audit_events;
create policy audit_member_read on public.audit_events
for select to authenticated using (is_org_member(organization_id));
drop policy if exists audit_member_insert on public.audit_events;
drop policy if exists audit_member_update on public.audit_events;
drop policy if exists audit_member_delete on public.audit_events;
