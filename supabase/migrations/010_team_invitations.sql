-- Organization invitation records and tenant/role-aware policies.
create table if not exists public.organization_invitations (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  email text not null,
  role text not null default 'recruiter' check (role in ('admin','recruiter','hiring_manager','viewer')),
  invited_by uuid not null references public.profiles(id) on delete restrict,
  token_hash text not null,
  expires_at timestamptz not null,
  accepted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint organization_invitations_expiry_check check (expires_at > created_at)
);

create index if not exists organization_invitations_org_created_idx
  on public.organization_invitations (organization_id, created_at desc);
create index if not exists organization_invitations_token_hash_idx
  on public.organization_invitations (token_hash);
create unique index if not exists organization_invitations_pending_unique
  on public.organization_invitations (organization_id, lower(email))
  where accepted_at is null;

alter table public.organization_invitations enable row level security;
drop policy if exists "organization admins manage invitations" on public.organization_invitations;
create policy "organization admins manage invitations"
  on public.organization_invitations for all to authenticated
  using (exists (
    select 1 from public.organization_members om
    where om.organization_id = organization_invitations.organization_id
      and om.user_id = (select auth.uid())
      and om.role in ('owner','admin')
  ))
  with check (exists (
    select 1 from public.organization_members om
    where om.organization_id = organization_invitations.organization_id
      and om.user_id = (select auth.uid())
      and om.role in ('owner','admin')
  ));
drop policy if exists "organization invitations visible to members" on public.organization_invitations;
create policy "organization invitations visible to members"
  on public.organization_invitations for select to authenticated
  using (exists (
    select 1 from public.organization_members om
    where om.organization_id = organization_invitations.organization_id
      and om.user_id = (select auth.uid())
  ));
