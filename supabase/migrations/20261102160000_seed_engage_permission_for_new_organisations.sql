-- Seed the Engage communication permission for organisations created after this migration.
create or replace function public.seed_organization_engage_permission()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  insert into public.organization_role_permissions (organization_id, role_id, permission_key, allowed)
  select r.organization_id, r.id, 'candidates.communicate',
         case when r.role_key in ('owner','admin','recruiter','hiring_manager') then true else false end
  from public.organization_roles r
  where r.organization_id = new.id
  on conflict (role_id, permission_key) do nothing;
  return new;
end;
$$;

drop trigger if exists z_organizations_seed_engage_permission on public.organizations;
create trigger z_organizations_seed_engage_permission
after insert on public.organizations
for each row execute function public.seed_organization_engage_permission();

revoke all on function public.seed_organization_engage_permission() from public, anon, authenticated;
