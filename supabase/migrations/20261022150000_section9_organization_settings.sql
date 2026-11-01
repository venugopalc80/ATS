-- Versioned organisation customisation; each save appends a new immutable version.
create table if not exists public.organization_settings_versions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  version integer not null check (version > 0),
  settings jsonb not null check (jsonb_typeof(settings) = 'object'),
  updated_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  unique (organization_id, version)
);
create index if not exists organization_settings_versions_latest_idx
  on public.organization_settings_versions(organization_id, version desc);
alter table public.organization_settings_versions enable row level security;
create policy organization_settings_versions_member_read
  on public.organization_settings_versions for select to authenticated
  using (public.is_org_member(organization_id));
revoke insert, update, delete on public.organization_settings_versions from anon, authenticated;
grant select on public.organization_settings_versions to authenticated;