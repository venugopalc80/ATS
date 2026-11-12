-- Organisation-scoped reusable tags and candidate assignments.
create table if not exists public.candidate_tags (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete cascade,
    name text not null check (length(trim(name)) between 1 and 50),
    colour text not null default '#64748b' check (colour ~ '^#[0-9A-Fa-f]{6}$'),
    created_by uuid null references public.profiles(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint candidate_tags_org_name_unique unique (organization_id, name),
    constraint candidate_tags_id_org_unique unique (id, organization_id)
);

create table if not exists public.candidate_tag_assignments (
    organization_id uuid not null references public.organizations(id) on delete cascade,
    candidate_id uuid not null references public.candidates(id) on delete cascade,
    tag_id uuid not null,
    assigned_by uuid null references public.profiles(id) on delete set null,
    created_at timestamptz not null default now(),
    primary key (candidate_id, tag_id),
    constraint candidate_tag_assignments_tag_org_fk
      foreign key (tag_id, organization_id)
      references public.candidate_tags(id, organization_id) on delete cascade
);

create unique index if not exists candidate_tags_org_name_ci_unique
  on public.candidate_tags (organization_id, lower(name));
create index if not exists candidate_tag_assignments_org_tag_idx
  on public.candidate_tag_assignments (organization_id, tag_id);
create index if not exists candidate_tag_assignments_org_candidate_idx
  on public.candidate_tag_assignments (organization_id, candidate_id);

-- Keep assignments tenant-consistent even if a future writer bypasses the API.
create or replace function public.validate_candidate_tag_assignment()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
begin
  if not exists (
    select 1 from public.candidates c
    where c.id = new.candidate_id and c.organization_id = new.organization_id
  ) then
    raise exception 'Candidate and tag assignment must belong to the same organisation'
      using errcode = '23514';
  end if;
  return new;
end;
$$;

revoke execute on function public.validate_candidate_tag_assignment() from public, anon, authenticated;

drop trigger if exists candidate_tag_assignment_tenant_guard on public.candidate_tag_assignments;
create trigger candidate_tag_assignment_tenant_guard
before insert or update of organization_id, candidate_id, tag_id
on public.candidate_tag_assignments
for each row execute function public.validate_candidate_tag_assignment();

alter table public.candidate_tags enable row level security;
alter table public.candidate_tag_assignments enable row level security;

drop policy if exists candidate_tags_member_read on public.candidate_tags;
create policy candidate_tags_member_read on public.candidate_tags
  for select to authenticated using (public.is_org_member(organization_id));
-- Mutations go through the authenticated backend API, which applies role checks.
-- Do not grant direct browser-role writes that could bypass admin-only tag management.

drop policy if exists candidate_tag_assignments_member_read on public.candidate_tag_assignments;
create policy candidate_tag_assignments_member_read on public.candidate_tag_assignments
  for select to authenticated using (public.is_org_member(organization_id));
-- Assignment mutations also go through the backend API after membership checks.

comment on table public.candidate_tags is 'Reusable tags scoped to one organisation.';
comment on table public.candidate_tag_assignments is 'Organisation-scoped candidate-to-tag assignments.';