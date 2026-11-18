-- AQERITH granular, organisation-scoped permissions.
-- Standard roles are editable templates; per-member overrides are time-bound and auditable.

create table if not exists public.permission_catalog (
  permission_key text primary key,
  category text not null,
  label text not null,
  description text not null,
  sensitive boolean not null default false,
  created_at timestamptz not null default now()
);

insert into public.permission_catalog (permission_key, category, label, description, sensitive) values
  ('jobs.read','jobs','View vacancies','View organisation vacancies',false),
  ('jobs.create','jobs','Create vacancies','Create new vacancies',false),
  ('jobs.update','jobs','Edit vacancies','Edit vacancy details and status',false),
  ('jobs.delete','jobs','Delete vacancies','Delete vacancies',true),
  ('candidates.read','candidates','View candidates','View candidate profiles',false),
  ('candidates.create','candidates','Create candidates','Create candidate profiles',false),
  ('candidates.update','candidates','Edit candidates','Edit candidate profiles',false),
  ('candidates.delete','candidates','Delete candidates','Delete candidate profiles',true),
  ('candidates.documents.read','candidate_documents','View CVs and documents','Preview and download candidate documents',true),
  ('candidates.documents.upload','candidate_documents','Upload CVs and documents','Upload candidate documents and CVs',true),
  ('candidates.documents.delete','candidate_documents','Delete CVs and documents','Delete candidate documents',true),
  ('applications.read','applications','View applications','View applications and pipeline records',false),
  ('applications.create','applications','Create applications','Create application records',false),
  ('applications.update','applications','Update applications','Update application stages and decisions',false),
  ('applications.delete','applications','Delete applications','Delete application records',true),
  ('interviews.read','interviews','View interviews','View interview schedules and feedback',false),
  ('interviews.create','interviews','Schedule interviews','Create interview records',false),
  ('interviews.update','interviews','Update interviews','Update interview details and outcomes',false),
  ('interviews.delete','interviews','Delete interviews','Delete interview records',true),
  ('offers.read','offers','View offers','View candidate offers',true),
  ('offers.create','offers','Create offers','Prepare candidate offers',true),
  ('offers.update','offers','Update offers','Update offer status and details',true),
  ('offers.delete','offers','Delete offers','Delete offer records',true),
  ('placements.read','placements','View placements','View placement records',false),
  ('placements.create','placements','Create placements','Create placement records',false),
  ('placements.update','placements','Update placements','Update placement records',false),
  ('placements.delete','placements','Delete placements','Delete placement records',true),
  ('clients.read','clients','View clients','View client organisations',false),
  ('clients.create','clients','Create clients','Create client organisations',false),
  ('clients.update','clients','Edit clients','Edit client organisations',false),
  ('clients.delete','clients','Delete clients','Delete client organisations',true),
  ('reports.read','reports','View reports','View recruitment reports',false),
  ('reports.export','reports','Export reports','Export organisation recruitment data',true),
  ('team.read','team','View team','View organisation team members',false),
  ('team.invite','team','Invite team members','Invite new organisation members',true),
  ('team.manage_roles','team','Manage roles and permissions','Create roles and change team permissions',true),
  ('organization.settings.manage','organization','Manage organisation settings','Change organisation-wide settings',true),
  ('organization.audit.read','organization','View audit history','View organisation audit history',true),
  ('privacy.manage','privacy','Manage privacy and data rights','Manage privacy notices, consent and data rights',true),
  ('integrations.manage','integrations','Manage integrations','Configure organisation integrations and webhooks',true),
  ('billing.manage','billing','Manage billing','Manage plans, payment methods and subscriptions',true),
  ('ai.use','ai','Use AI assistance','Use AI-powered recruitment assistance',false),
  ('ai.configure','ai','Configure AI','Configure AI providers, models and controls',true),
  ('ownership.transfer','organization','Transfer ownership','Transfer organisation ownership',true)
on conflict (permission_key) do update set
  category = excluded.category,
  label = excluded.label,
  description = excluded.description,
  sensitive = excluded.sensitive;

create table if not exists public.organization_roles (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  role_key text not null,
  name text not null,
  description text,
  is_system boolean not null default false,
  is_active boolean not null default true,
  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, role_key),
  unique (organization_id, id)
);

create table if not exists public.organization_role_permissions (
  organization_id uuid not null,
  role_id uuid not null,
  permission_key text not null references public.permission_catalog(permission_key) on delete cascade,
  allowed boolean not null default false,
  updated_by uuid references public.profiles(id) on delete set null,
  updated_at timestamptz not null default now(),
  primary key (role_id, permission_key),
  foreign key (organization_id, role_id)
    references public.organization_roles(organization_id, id) on delete cascade
);

create table if not exists public.organization_member_permission_overrides (
  organization_id uuid not null,
  user_id uuid not null,
  permission_key text not null references public.permission_catalog(permission_key) on delete cascade,
  effect text not null check (effect in ('allow','deny')),
  reason text,
  expires_at timestamptz,
  granted_by uuid not null references public.profiles(id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (organization_id, user_id, permission_key),
  foreign key (organization_id, user_id)
    references public.organization_members(organization_id, user_id) on delete cascade,
  check (expires_at is null or expires_at > created_at)
);

alter table public.organization_members
  add column if not exists custom_role_id uuid;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'organization_members_custom_role_fkey'
      and conrelid = 'public.organization_members'::regclass
  ) then
    alter table public.organization_members
      add constraint organization_members_custom_role_fkey
      foreign key (organization_id, custom_role_id)
      references public.organization_roles(organization_id, id)
      on delete restrict;
  end if;
end $$;

create index if not exists organization_roles_org_active_idx
  on public.organization_roles(organization_id, is_active);
create index if not exists organization_member_overrides_user_idx
  on public.organization_member_permission_overrides(organization_id, user_id);
create index if not exists organization_member_overrides_expiry_idx
  on public.organization_member_permission_overrides(expires_at)
  where expires_at is not null;

-- Seed editable standard role templates for all existing organisations.
insert into public.organization_roles (organization_id, role_key, name, description, is_system)
select o.id, r.role_key, r.name, r.description, true
from public.organizations o
cross join (values
  ('owner','Owner','Full organisation ownership and control'),
  ('admin','Administrator','Organisation administration and recruitment operations'),
  ('recruiter','Recruiter','Recruitment workflow operations'),
  ('hiring_manager','Hiring Manager','Vacancy and hiring decision collaboration'),
  ('viewer','Viewer','Read-only workspace access')
) as r(role_key, name, description)
on conflict (organization_id, role_key) do nothing;

-- Default templates are intentionally permissive for hiring managers on vacancy work.
-- Owners and administrators may customise these templates per organisation.
with defaults(role_key, permission_key, allowed) as (
  values
  ('owner','jobs.read',true),('owner','jobs.create',true),('owner','jobs.update',true),('owner','jobs.delete',true),
  ('owner','candidates.read',true),('owner','candidates.create',true),('owner','candidates.update',true),('owner','candidates.delete',true),
  ('owner','candidates.documents.read',true),('owner','candidates.documents.upload',true),('owner','candidates.documents.delete',true),
  ('owner','applications.read',true),('owner','applications.create',true),('owner','applications.update',true),('owner','applications.delete',true),
  ('owner','interviews.read',true),('owner','interviews.create',true),('owner','interviews.update',true),('owner','interviews.delete',true),
  ('owner','offers.read',true),('owner','offers.create',true),('owner','offers.update',true),('owner','offers.delete',true),
  ('owner','placements.read',true),('owner','placements.create',true),('owner','placements.update',true),('owner','placements.delete',true),
  ('owner','clients.read',true),('owner','clients.create',true),('owner','clients.update',true),('owner','clients.delete',true),
  ('owner','reports.read',true),('owner','reports.export',true),('owner','team.read',true),('owner','team.invite',true),
  ('owner','team.manage_roles',true),('owner','organization.settings.manage',true),('owner','organization.audit.read',true),
  ('owner','privacy.manage',true),('owner','integrations.manage',true),('owner','billing.manage',true),('owner','ai.use',true),
  ('owner','ai.configure',true),('owner','ownership.transfer',true),

  ('admin','jobs.read',true),('admin','jobs.create',true),('admin','jobs.update',true),('admin','jobs.delete',true),
  ('admin','candidates.read',true),('admin','candidates.create',true),('admin','candidates.update',true),('admin','candidates.delete',true),
  ('admin','candidates.documents.read',true),('admin','candidates.documents.upload',true),('admin','candidates.documents.delete',true),
  ('admin','applications.read',true),('admin','applications.create',true),('admin','applications.update',true),('admin','applications.delete',true),
  ('admin','interviews.read',true),('admin','interviews.create',true),('admin','interviews.update',true),('admin','interviews.delete',true),
  ('admin','offers.read',true),('admin','offers.create',true),('admin','offers.update',true),('admin','offers.delete',true),
  ('admin','placements.read',true),('admin','placements.create',true),('admin','placements.update',true),('admin','placements.delete',true),
  ('admin','clients.read',true),('admin','clients.create',true),('admin','clients.update',true),('admin','clients.delete',true),
  ('admin','reports.read',true),('admin','reports.export',true),('admin','team.read',true),('admin','team.invite',true),
  ('admin','team.manage_roles',true),('admin','organization.settings.manage',true),('admin','organization.audit.read',true),
  ('admin','privacy.manage',true),('admin','integrations.manage',true),('admin','billing.manage',true),('admin','ai.use',true),
  ('admin','ai.configure',true),

  ('recruiter','jobs.read',true),('recruiter','jobs.create',true),('recruiter','jobs.update',true),
  ('recruiter','candidates.read',true),('recruiter','candidates.create',true),('recruiter','candidates.update',true),
  ('recruiter','candidates.documents.read',true),('recruiter','candidates.documents.upload',true),
  ('recruiter','applications.read',true),('recruiter','applications.create',true),('recruiter','applications.update',true),
  ('recruiter','interviews.read',true),('recruiter','interviews.create',true),('recruiter','interviews.update',true),
  ('recruiter','offers.read',true),('recruiter','offers.create',true),('recruiter','offers.update',true),
  ('recruiter','placements.read',true),('recruiter','placements.create',true),('recruiter','placements.update',true),
  ('recruiter','clients.read',true),('recruiter','clients.create',true),('recruiter','clients.update',true),
  ('recruiter','reports.read',true),('recruiter','team.read',true),('recruiter','ai.use',true),

  ('hiring_manager','jobs.read',true),('hiring_manager','jobs.create',true),('hiring_manager','jobs.update',true),
  ('hiring_manager','candidates.read',true),('hiring_manager','candidates.update',true),
  ('hiring_manager','candidates.documents.read',true),
  ('hiring_manager','applications.read',true),('hiring_manager','applications.update',true),
  ('hiring_manager','interviews.read',true),('hiring_manager','interviews.create',true),('hiring_manager','interviews.update',true),
  ('hiring_manager','offers.read',true),('hiring_manager','offers.update',true),
  ('hiring_manager','placements.read',true),('hiring_manager','clients.read',true),('hiring_manager','reports.read',true),('hiring_manager','ai.use',true),

  ('viewer','jobs.read',true),('viewer','candidates.read',true),('viewer','applications.read',true),
  ('viewer','interviews.read',true),('viewer','offers.read',true),('viewer','placements.read',true),
  ('viewer','clients.read',true),('viewer','reports.read',true),('viewer','team.read',true)
)
insert into public.organization_role_permissions (organization_id, role_id, permission_key, allowed)
select r.organization_id, r.id, d.permission_key, d.allowed
from public.organization_roles r
join defaults d on d.role_key = r.role_key
on conflict (role_id, permission_key) do nothing;

-- New organisations automatically receive the same editable role templates.
create or replace function public.seed_organization_roles()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  role_row record;
begin
  for role_row in
    select * from (values
      ('owner','Owner','Full organisation ownership and control'),
      ('admin','Administrator','Organisation administration and recruitment operations'),
      ('recruiter','Recruiter','Recruitment workflow operations'),
      ('hiring_manager','Hiring Manager','Vacancy and hiring decision collaboration'),
      ('viewer','Viewer','Read-only workspace access')
    ) as roles(role_key, name, description)
  loop
    insert into public.organization_roles (organization_id, role_key, name, description, is_system)
    values (new.id, role_row.role_key, role_row.name, role_row.description, true)
    on conflict (organization_id, role_key) do nothing;
  end loop;

  insert into public.organization_role_permissions (organization_id, role_id, permission_key, allowed)
  select r.organization_id, r.id, d.permission_key, d.allowed
  from public.organization_roles r
  join (
    select * from (values
      ('owner','jobs.read',true),('owner','jobs.create',true),('owner','jobs.update',true),('owner','jobs.delete',true),
      ('owner','candidates.read',true),('owner','candidates.create',true),('owner','candidates.update',true),('owner','candidates.delete',true),
      ('owner','candidates.documents.read',true),('owner','candidates.documents.upload',true),('owner','candidates.documents.delete',true),
      ('owner','applications.read',true),('owner','applications.create',true),('owner','applications.update',true),('owner','applications.delete',true),
      ('owner','interviews.read',true),('owner','interviews.create',true),('owner','interviews.update',true),('owner','interviews.delete',true),
      ('owner','offers.read',true),('owner','offers.create',true),('owner','offers.update',true),('owner','offers.delete',true),
      ('owner','placements.read',true),('owner','placements.create',true),('owner','placements.update',true),('owner','placements.delete',true),
      ('owner','clients.read',true),('owner','clients.create',true),('owner','clients.update',true),('owner','clients.delete',true),
      ('owner','reports.read',true),('owner','reports.export',true),('owner','team.read',true),('owner','team.invite',true),('owner','team.manage_roles',true),
      ('owner','organization.settings.manage',true),('owner','organization.audit.read',true),('owner','privacy.manage',true),
      ('owner','integrations.manage',true),('owner','billing.manage',true),('owner','ai.use',true),('owner','ai.configure',true),('owner','ownership.transfer',true),
      ('admin','jobs.read',true),('admin','jobs.create',true),('admin','jobs.update',true),('admin','jobs.delete',true),
      ('admin','candidates.read',true),('admin','candidates.create',true),('admin','candidates.update',true),('admin','candidates.delete',true),
      ('admin','candidates.documents.read',true),('admin','candidates.documents.upload',true),('admin','candidates.documents.delete',true),
      ('admin','applications.read',true),('admin','applications.create',true),('admin','applications.update',true),('admin','applications.delete',true),
      ('admin','interviews.read',true),('admin','interviews.create',true),('admin','interviews.update',true),('admin','interviews.delete',true),
      ('admin','offers.read',true),('admin','offers.create',true),('admin','offers.update',true),('admin','offers.delete',true),
      ('admin','placements.read',true),('admin','placements.create',true),('admin','placements.update',true),('admin','placements.delete',true),
      ('admin','clients.read',true),('admin','clients.create',true),('admin','clients.update',true),('admin','clients.delete',true),
      ('admin','reports.read',true),('admin','reports.export',true),('admin','team.read',true),('admin','team.invite',true),('admin','team.manage_roles',true),
      ('admin','organization.settings.manage',true),('admin','organization.audit.read',true),('admin','privacy.manage',true),
      ('admin','integrations.manage',true),('admin','billing.manage',true),('admin','ai.use',true),('admin','ai.configure',true),
      ('recruiter','jobs.read',true),('recruiter','jobs.create',true),('recruiter','jobs.update',true),
      ('recruiter','candidates.read',true),('recruiter','candidates.create',true),('recruiter','candidates.update',true),
      ('recruiter','candidates.documents.read',true),('recruiter','candidates.documents.upload',true),
      ('recruiter','applications.read',true),('recruiter','applications.create',true),('recruiter','applications.update',true),
      ('recruiter','interviews.read',true),('recruiter','interviews.create',true),('recruiter','interviews.update',true),
      ('recruiter','offers.read',true),('recruiter','offers.create',true),('recruiter','offers.update',true),
      ('recruiter','placements.read',true),('recruiter','placements.create',true),('recruiter','placements.update',true),
      ('recruiter','clients.read',true),('recruiter','clients.create',true),('recruiter','clients.update',true),
      ('recruiter','reports.read',true),('recruiter','team.read',true),('recruiter','ai.use',true),
      ('hiring_manager','jobs.read',true),('hiring_manager','jobs.create',true),('hiring_manager','jobs.update',true),
      ('hiring_manager','candidates.read',true),('hiring_manager','candidates.update',true),('hiring_manager','candidates.documents.read',true),
      ('hiring_manager','applications.read',true),('hiring_manager','applications.update',true),
      ('hiring_manager','interviews.read',true),('hiring_manager','interviews.create',true),('hiring_manager','interviews.update',true),
      ('hiring_manager','offers.read',true),('hiring_manager','offers.update',true),('hiring_manager','placements.read',true),('hiring_manager','clients.read',true),('hiring_manager','reports.read',true),('hiring_manager','ai.use',true),
      ('viewer','jobs.read',true),('viewer','candidates.read',true),('viewer','applications.read',true),('viewer','interviews.read',true),
      ('viewer','offers.read',true),('viewer','placements.read',true),('viewer','clients.read',true),('viewer','reports.read',true),('viewer','team.read',true)
    ) as seed(role_key, permission_key, allowed)
  ) d on d.role_key = r.role_key
  where r.organization_id = new.id
  on conflict (role_id, permission_key) do nothing;

  return new;
end;
$$;

drop trigger if exists organizations_seed_roles on public.organizations;
create trigger organizations_seed_roles
after insert on public.organizations
for each row execute function public.seed_organization_roles();

alter table public.permission_catalog enable row level security;
alter table public.organization_roles enable row level security;
alter table public.organization_role_permissions enable row level security;
alter table public.organization_member_permission_overrides enable row level security;

drop policy if exists permission_catalog_authenticated_read on public.permission_catalog;
create policy permission_catalog_authenticated_read on public.permission_catalog
for select to authenticated using (true);

drop policy if exists organization_roles_member_read on public.organization_roles;
create policy organization_roles_member_read on public.organization_roles
for select to authenticated using (public.is_org_member(organization_id));

drop policy if exists organization_role_permissions_member_read on public.organization_role_permissions;
create policy organization_role_permissions_member_read on public.organization_role_permissions
for select to authenticated using (public.is_org_member(organization_id));

drop policy if exists member_permission_overrides_self_or_admin_read on public.organization_member_permission_overrides;
create policy member_permission_overrides_self_or_admin_read on public.organization_member_permission_overrides
for select to authenticated using (
  user_id = auth.uid() or public.is_org_admin(organization_id)
);

-- No direct authenticated writes: all permission mutations go through audited backend APIs.
revoke insert, update, delete on public.permission_catalog from anon, authenticated;
revoke insert, update, delete on public.organization_roles from anon, authenticated;
revoke insert, update, delete on public.organization_role_permissions from anon, authenticated;
revoke insert, update, delete on public.organization_member_permission_overrides from anon, authenticated;
