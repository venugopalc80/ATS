-- AQERITH RBAC v2: resource-level recruitment access.
-- Existing members default to assigned-resource scope; owners/admins retain
-- organisation-wide access. Organisation-wide scope can be granted explicitly.

-- Composite keys keep every assignment tenant-bound at the database level.
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'jobs_id_organization_unique') then
    alter table public.jobs add constraint jobs_id_organization_unique unique (id, organization_id);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'clients_id_organization_unique') then
    alter table public.clients add constraint clients_id_organization_unique unique (id, organization_id);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'candidates_id_organization_unique') then
    alter table public.candidates add constraint candidates_id_organization_unique unique (id, organization_id);
  end if;
end $$;

create table if not exists public.organization_member_access_scopes (
    organization_id uuid not null references public.organizations(id) on delete cascade,
    user_id uuid not null references public.profiles(id) on delete cascade,
    scope text not null default 'assigned' check (scope in ('assigned', 'organization')),
    updated_at timestamptz not null default now(),
    updated_by uuid references public.profiles(id) on delete set null,
    primary key (organization_id, user_id),
    foreign key (organization_id, user_id)
      references public.organization_members(organization_id, user_id) on delete cascade
);

insert into public.organization_member_access_scopes (organization_id, user_id, scope)
select organization_id, user_id,
       case when role in ('owner', 'admin') then 'organization' else 'assigned' end
from public.organization_members
on conflict (organization_id, user_id) do nothing;

create table if not exists public.recruitment_teams (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete cascade,
    name text not null,
    description text,
    created_by uuid references public.profiles(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (organization_id, id),
    unique (organization_id, name)
);

create table if not exists public.recruitment_team_members (
    organization_id uuid not null,
    team_id uuid not null,
    user_id uuid not null,
    created_at timestamptz not null default now(),
    primary key (team_id, user_id),
    foreign key (organization_id, team_id)
      references public.recruitment_teams(organization_id, id) on delete cascade,
    foreign key (organization_id, user_id)
      references public.organization_members(organization_id, user_id) on delete cascade
);

create table if not exists public.recruitment_team_jobs (
    organization_id uuid not null,
    team_id uuid not null,
    job_id uuid not null,
    created_at timestamptz not null default now(),
    primary key (team_id, job_id),
    foreign key (organization_id, team_id)
      references public.recruitment_teams(organization_id, id) on delete cascade,
    foreign key (job_id, organization_id)
      references public.jobs(id, organization_id) on delete cascade
);

create table if not exists public.recruitment_team_clients (
    organization_id uuid not null,
    team_id uuid not null,
    client_id uuid not null,
    created_at timestamptz not null default now(),
    primary key (team_id, client_id),
    foreign key (organization_id, team_id)
      references public.recruitment_teams(organization_id, id) on delete cascade,
    foreign key (client_id, organization_id)
      references public.clients(id, organization_id) on delete cascade
);

create table if not exists public.candidate_access_assignments (
    organization_id uuid not null,
    candidate_id uuid not null,
    user_id uuid not null,
    assigned_by uuid references public.profiles(id) on delete set null,
    created_at timestamptz not null default now(),
    primary key (candidate_id, user_id),
    foreign key (candidate_id, organization_id)
      references public.candidates(id, organization_id) on delete cascade,
    foreign key (organization_id, user_id)
      references public.organization_members(organization_id, user_id) on delete cascade
);

create table if not exists public.application_access_assignments (
    organization_id uuid not null,
    application_id uuid not null,
    user_id uuid not null,
    assigned_by uuid references public.profiles(id) on delete set null,
    created_at timestamptz not null default now(),
    primary key (application_id, user_id),
    foreign key (application_id, organization_id)
      references public.applications(id, organization_id) on delete cascade,
    foreign key (organization_id, user_id)
      references public.organization_members(organization_id, user_id) on delete cascade
);

create table if not exists public.client_access_assignments (
    organization_id uuid not null,
    client_id uuid not null,
    user_id uuid not null,
    assigned_by uuid references public.profiles(id) on delete set null,
    created_at timestamptz not null default now(),
    primary key (client_id, user_id),
    foreign key (client_id, organization_id)
      references public.clients(id, organization_id) on delete cascade,
    foreign key (organization_id, user_id)
      references public.organization_members(organization_id, user_id) on delete cascade
);

create index if not exists idx_team_members_user on public.recruitment_team_members(organization_id, user_id);
create index if not exists idx_team_jobs_job on public.recruitment_team_jobs(organization_id, job_id);
create index if not exists idx_team_clients_client on public.recruitment_team_clients(organization_id, client_id);
create index if not exists idx_candidate_access_user on public.candidate_access_assignments(organization_id, user_id);
create index if not exists idx_client_access_user on public.client_access_assignments(organization_id, user_id);
create index if not exists idx_application_access_user on public.application_access_assignments(organization_id, user_id);
create index if not exists idx_jobs_recruiter_scope on public.jobs(organization_id, recruiter_id);
create index if not exists idx_jobs_hiring_manager_scope on public.jobs(organization_id, hiring_manager_id);
create index if not exists idx_applications_job_candidate_scope on public.applications(organization_id, job_id, candidate_id);

create or replace function public.has_organization_wide_access(target_org uuid, target_user uuid default auth.uid())
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.organization_members m
    left join public.organization_member_access_scopes s
      on s.organization_id = m.organization_id and s.user_id = m.user_id
    where m.organization_id = target_org
      and m.user_id = target_user
      and (
        m.role in ('owner', 'admin')
        or coalesce(s.scope, 'assigned') = 'organization'
      )
  );
$$;

create or replace function public.can_access_job(target_job uuid, target_org uuid, target_user uuid default auth.uid())
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select public.has_organization_wide_access(target_org, target_user)
    or exists (
      select 1 from public.jobs j
      where j.id = target_job and j.organization_id = target_org
        and (j.recruiter_id = target_user or j.hiring_manager_id = target_user)
    )
    or exists (
      select 1
      from public.recruitment_team_jobs tj
      join public.recruitment_team_members tm
        on tm.organization_id = tj.organization_id and tm.team_id = tj.team_id
      where tj.organization_id = target_org and tj.job_id = target_job
        and tm.user_id = target_user
    );
$$;

create or replace function public.can_access_client(target_client uuid, target_org uuid, target_user uuid default auth.uid())
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select public.has_organization_wide_access(target_org, target_user)
    or exists (
      select 1 from public.client_access_assignments ca
      where ca.organization_id = target_org and ca.client_id = target_client and ca.user_id = target_user
    )
    or exists (
      select 1
      from public.recruitment_team_clients tc
      join public.recruitment_team_members tm
        on tm.organization_id = tc.organization_id and tm.team_id = tc.team_id
      where tc.organization_id = target_org and tc.client_id = target_client
        and tm.user_id = target_user
    )
    or exists (
      select 1 from public.jobs j
      where j.organization_id = target_org and j.client_id = target_client
        and public.can_access_job(j.id, target_org, target_user)
    );
$$;

create or replace function public.can_access_candidate(target_candidate uuid, target_org uuid, target_user uuid default auth.uid())
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select public.has_organization_wide_access(target_org, target_user)
    or exists (
      select 1 from public.candidate_access_assignments ca
      where ca.organization_id = target_org and ca.candidate_id = target_candidate and ca.user_id = target_user
    )
    or exists (
      select 1
      from public.applications a
      where a.organization_id = target_org and a.candidate_id = target_candidate
        and (
          public.can_access_job(a.job_id, target_org, target_user)
          or exists (
            select 1 from public.application_access_assignments aa
            where aa.organization_id = target_org
              and aa.application_id = a.id
              and aa.user_id = target_user
          )
        )
    );
$$;

create or replace function public.can_access_application(target_application uuid, target_org uuid, target_user uuid default auth.uid())
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select public.has_organization_wide_access(target_org, target_user)
    or exists (
      select 1 from public.applications a
      where a.id = target_application and a.organization_id = target_org
        and (
          public.can_access_job(a.job_id, target_org, target_user)
          or exists (
            select 1 from public.application_access_assignments aa
            where aa.organization_id = target_org
              and aa.application_id = a.id
              and aa.user_id = target_user
          )
        )
    );
$$;

-- Keep the functions callable by authenticated RLS policies, not by anonymous users.
revoke all on function public.has_organization_wide_access(uuid, uuid) from public, anon;
revoke all on function public.can_access_job(uuid, uuid, uuid) from public, anon;
revoke all on function public.can_access_client(uuid, uuid, uuid) from public, anon;
revoke all on function public.can_access_candidate(uuid, uuid, uuid) from public, anon;
revoke all on function public.can_access_application(uuid, uuid, uuid) from public, anon;
grant execute on function public.has_organization_wide_access(uuid, uuid) to authenticated, service_role;
grant execute on function public.can_access_job(uuid, uuid, uuid) to authenticated, service_role;
grant execute on function public.can_access_client(uuid, uuid, uuid) to authenticated, service_role;
grant execute on function public.can_access_candidate(uuid, uuid, uuid) to authenticated, service_role;
grant execute on function public.can_access_application(uuid, uuid, uuid) to authenticated, service_role;


-- Permission + resource scoped RLS. The API service role is separately guarded
-- by the backend; direct authenticated Data API access must pass both controls.
create or replace function public.has_effective_org_permission(
  target_org uuid, target_permission text
) returns boolean
language sql stable security definer set search_path = public
as $$
  select exists (
    select 1
    from public.organization_members m
    left join public.organization_roles role_template
      on role_template.organization_id = m.organization_id
     and ((m.custom_role_id is not null and role_template.id = m.custom_role_id)
       or (m.custom_role_id is null and role_template.role_key = m.role))
    left join public.organization_role_permissions rp
      on rp.organization_id = m.organization_id
     and rp.role_id = role_template.id
     and rp.permission_key = target_permission
    left join public.organization_member_permission_overrides ov
      on ov.organization_id = m.organization_id
     and ov.user_id = m.user_id
     and ov.permission_key = target_permission
     and (ov.expires_at is null or ov.expires_at > now())
    where m.organization_id = target_org and m.user_id = auth.uid()
      and case
        when m.role = 'owner' then true
        when m.role = 'admin' and target_permission = 'ownership.transfer' then false
        when ov.effect is not null then ov.effect = 'allow'
        else coalesce(rp.allowed, false)
      end
  );
$$;
revoke all on function public.has_effective_org_permission(uuid, text) from public, anon;
grant execute on function public.has_effective_org_permission(uuid, text) to authenticated, service_role;

-- Remove legacy organisation-wide member policies before installing scoped policies.
-- PostgreSQL combines permissive policies with OR, so leaving any broad policy
-- in place would silently bypass the resource-level checks below.
drop policy if exists jobs_member_all on public.jobs;
drop policy if exists candidates_member_all on public.candidates;
drop policy if exists applications_member_all on public.applications;
drop policy if exists clients_member_all on public.clients;
drop policy if exists interviews_member_all on public.interviews;
drop policy if exists offers_member_all on public.offers;
drop policy if exists placements_member_all on public.placements;

-- Jobs
drop policy if exists jobs_resource_scope on public.jobs;
create policy jobs_resource_select on public.jobs for select to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'jobs.read')
  and public.can_access_job(id, organization_id));
create policy jobs_resource_insert on public.jobs for insert to authenticated
with check (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'jobs.create')
  and public.has_organization_wide_access(organization_id));
create policy jobs_resource_update on public.jobs for update to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'jobs.update')
  and public.can_access_job(id, organization_id))
with check (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'jobs.update')
  and public.can_access_job(id, organization_id));
create policy jobs_resource_delete on public.jobs for delete to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'jobs.delete')
  and public.can_access_job(id, organization_id));

-- Candidates
drop policy if exists candidates_resource_scope on public.candidates;
create policy candidates_resource_select on public.candidates for select to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'candidates.read')
  and public.can_access_candidate(id, organization_id));
create policy candidates_resource_insert on public.candidates for insert to authenticated
with check (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'candidates.create')
  and public.has_organization_wide_access(organization_id));
create policy candidates_resource_update on public.candidates for update to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'candidates.update')
  and public.can_access_candidate(id, organization_id))
with check (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'candidates.update')
  and public.can_access_candidate(id, organization_id));
create policy candidates_resource_delete on public.candidates for delete to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'candidates.delete')
  and public.can_access_candidate(id, organization_id));

-- Applications
drop policy if exists applications_resource_scope on public.applications;
create policy applications_resource_select on public.applications for select to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'applications.read')
  and public.can_access_application(id, organization_id));
create policy applications_resource_insert on public.applications for insert to authenticated
with check (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'applications.create')
  and public.can_access_job(job_id, organization_id)
  and public.can_access_candidate(candidate_id, organization_id));
create policy applications_resource_update on public.applications for update to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'applications.update')
  and public.can_access_application(id, organization_id))
with check (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'applications.update')
  and public.can_access_job(job_id, organization_id)
  and public.can_access_candidate(candidate_id, organization_id));
create policy applications_resource_delete on public.applications for delete to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'applications.delete')
  and public.can_access_application(id, organization_id));

-- Clients
drop policy if exists clients_resource_scope on public.clients;
create policy clients_resource_select on public.clients for select to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'clients.read')
  and public.can_access_client(id, organization_id));
create policy clients_resource_insert on public.clients for insert to authenticated
with check (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'clients.create')
  and public.has_organization_wide_access(organization_id));
create policy clients_resource_update on public.clients for update to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'clients.update')
  and public.can_access_client(id, organization_id))
with check (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'clients.update')
  and public.can_access_client(id, organization_id));
create policy clients_resource_delete on public.clients for delete to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'clients.delete')
  and public.can_access_client(id, organization_id));

-- Interview, offer and placement records inherit application visibility.
drop policy if exists interviews_resource_scope on public.interviews;
create policy interviews_resource_select on public.interviews for select to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'interviews.read')
  and exists (select 1 from public.applications a where a.id = interviews.application_id
    and public.can_access_application(a.id, interviews.organization_id)));
create policy interviews_resource_insert on public.interviews for insert to authenticated
with check (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'interviews.create')
  and exists (select 1 from public.applications a where a.id = interviews.application_id
    and public.can_access_application(a.id, interviews.organization_id)));
create policy interviews_resource_update on public.interviews for update to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'interviews.update')
  and exists (select 1 from public.applications a where a.id = interviews.application_id
    and public.can_access_application(a.id, interviews.organization_id)))
with check (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'interviews.update')
  and exists (select 1 from public.applications a where a.id = interviews.application_id
    and public.can_access_application(a.id, interviews.organization_id)));
create policy interviews_resource_delete on public.interviews for delete to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'interviews.delete')
  and exists (select 1 from public.applications a where a.id = interviews.application_id
    and public.can_access_application(a.id, interviews.organization_id)));

drop policy if exists offers_resource_scope on public.offers;
create policy offers_resource_select on public.offers for select to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'offers.read')
  and exists (select 1 from public.applications a where a.id = offers.application_id
    and public.can_access_application(a.id, offers.organization_id)));
create policy offers_resource_insert on public.offers for insert to authenticated
with check (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'offers.create')
  and exists (select 1 from public.applications a where a.id = offers.application_id
    and public.can_access_application(a.id, offers.organization_id)));
create policy offers_resource_update on public.offers for update to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'offers.update')
  and exists (select 1 from public.applications a where a.id = offers.application_id
    and public.can_access_application(a.id, offers.organization_id)))
with check (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'offers.update')
  and exists (select 1 from public.applications a where a.id = offers.application_id
    and public.can_access_application(a.id, offers.organization_id)));
create policy offers_resource_delete on public.offers for delete to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'offers.delete')
  and exists (select 1 from public.applications a where a.id = offers.application_id
    and public.can_access_application(a.id, offers.organization_id)));

drop policy if exists placements_resource_scope on public.placements;
create policy placements_resource_select on public.placements for select to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'placements.read')
  and public.can_access_application(application_id, organization_id));
create policy placements_resource_insert on public.placements for insert to authenticated
with check (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'placements.create')
  and public.can_access_application(application_id, organization_id));
create policy placements_resource_update on public.placements for update to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'placements.update')
  and public.can_access_application(application_id, organization_id))
with check (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'placements.update')
  and public.can_access_application(application_id, organization_id));
create policy placements_resource_delete on public.placements for delete to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'placements.delete')
  and public.can_access_application(application_id, organization_id));

-- Candidate documents and communications inherit candidate access and their own permission.
drop policy if exists candidate_documents_member_all on public.candidate_documents;
drop policy if exists candidate_documents_resource_scope on public.candidate_documents;
drop policy if exists candidate_documents_resource_insert on public.candidate_documents;
drop policy if exists candidate_documents_resource_update on public.candidate_documents;
drop policy if exists candidate_documents_resource_delete on public.candidate_documents;
create policy candidate_documents_resource_select on public.candidate_documents for select to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'candidates.documents.read')
  and public.can_access_candidate(candidate_id, organization_id));
create policy candidate_documents_resource_insert on public.candidate_documents for insert to authenticated
with check (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'candidates.documents.upload')
  and public.can_access_candidate(candidate_id, organization_id));
create policy candidate_documents_resource_update on public.candidate_documents for update to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'candidates.documents.upload')
  and public.can_access_candidate(candidate_id, organization_id))
with check (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'candidates.documents.upload')
  and public.can_access_candidate(candidate_id, organization_id));
create policy candidate_documents_resource_delete on public.candidate_documents for delete to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'candidates.documents.delete')
  and public.can_access_candidate(candidate_id, organization_id));

-- Prevent direct authenticated writes to access-control metadata; mutations go through audited API routes.
alter table public.organization_member_access_scopes enable row level security;
alter table public.recruitment_teams enable row level security;
alter table public.recruitment_team_members enable row level security;
alter table public.recruitment_team_jobs enable row level security;
alter table public.recruitment_team_clients enable row level security;
alter table public.candidate_access_assignments enable row level security;
alter table public.client_access_assignments enable row level security;
alter table public.application_access_assignments enable row level security;

do $$
declare t text;
begin
  foreach t in array array[
    'organization_member_access_scopes','recruitment_teams','recruitment_team_members',
    'recruitment_team_jobs','recruitment_team_clients','candidate_access_assignments',
    'client_access_assignments','application_access_assignments'
  ] loop
    execute format('revoke all on public.%I from anon, authenticated', t);
  end loop;
end $$;

grant select on public.organization_member_access_scopes, public.recruitment_teams,
  public.recruitment_team_members, public.recruitment_team_jobs,
  public.recruitment_team_clients, public.candidate_access_assignments,
  public.client_access_assignments, public.application_access_assignments to authenticated;

create policy access_scope_self_read on public.organization_member_access_scopes
for select to authenticated using (user_id = auth.uid() or public.has_organization_wide_access(organization_id));
create policy recruitment_teams_member_read on public.recruitment_teams
for select to authenticated using (public.is_org_member(organization_id));
create policy recruitment_team_members_member_read on public.recruitment_team_members
for select to authenticated using (public.is_org_member(organization_id));
create policy recruitment_team_jobs_member_read on public.recruitment_team_jobs
for select to authenticated using (public.is_org_member(organization_id));
create policy recruitment_team_clients_member_read on public.recruitment_team_clients
for select to authenticated using (public.is_org_member(organization_id));
create policy candidate_access_assignments_member_read on public.candidate_access_assignments
for select to authenticated using (user_id = auth.uid() or public.has_organization_wide_access(organization_id));
create policy client_access_assignments_member_read on public.client_access_assignments
for select to authenticated using (user_id = auth.uid() or public.has_organization_wide_access(organization_id));
create policy application_access_assignments_member_read on public.application_access_assignments
for select to authenticated using (user_id = auth.uid() or public.has_organization_wide_access(organization_id));

-- Candidate communications inherit the candidate's resource boundary.
drop policy if exists candidate_communications_member_read on public.candidate_communications;
drop policy if exists candidate_communications_permission_read on public.candidate_communications;
create policy candidate_communications_resource_read on public.candidate_communications
for select to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'candidates.communicate')
  and public.can_access_candidate(candidate_id, organization_id));

-- Private bucket policies: object paths are organization_id/candidate_id/document_id.ext.
drop policy if exists candidate_documents_authenticated_read on storage.objects;
drop policy if exists candidate_documents_authenticated_insert on storage.objects;
create policy candidate_documents_scoped_read on storage.objects
for select to authenticated
using (
  bucket_id = 'candidate-documents'
  and array_length(storage.foldername(name), 1) >= 2
  and public.has_effective_org_permission((storage.foldername(name))[1]::uuid, 'candidates.documents.read')
  and public.can_access_candidate(
    (storage.foldername(name))[2]::uuid,
    (storage.foldername(name))[1]::uuid
  )
);
create policy candidate_documents_scoped_insert on storage.objects
for insert to authenticated
with check (
  bucket_id = 'candidate-documents'
  and array_length(storage.foldername(name), 1) >= 2
  and public.has_effective_org_permission((storage.foldername(name))[1]::uuid, 'candidates.documents.upload')
  and public.can_access_candidate(
    (storage.foldername(name))[2]::uuid,
    (storage.foldername(name))[1]::uuid
  )
);
create policy candidate_documents_scoped_update on storage.objects
for update to authenticated
using (
  bucket_id = 'candidate-documents'
  and array_length(storage.foldername(name), 1) >= 2
  and public.has_effective_org_permission((storage.foldername(name))[1]::uuid, 'candidates.documents.upload')
  and public.can_access_candidate(
    (storage.foldername(name))[2]::uuid,
    (storage.foldername(name))[1]::uuid
  )
)
with check (
  bucket_id = 'candidate-documents'
  and array_length(storage.foldername(name), 1) >= 2
  and public.has_effective_org_permission((storage.foldername(name))[1]::uuid, 'candidates.documents.upload')
  and public.can_access_candidate(
    (storage.foldername(name))[2]::uuid,
    (storage.foldername(name))[1]::uuid
  )
);
create policy candidate_documents_scoped_delete on storage.objects
for delete to authenticated
using (
  bucket_id = 'candidate-documents'
  and array_length(storage.foldername(name), 1) >= 2
  and public.has_effective_org_permission((storage.foldername(name))[1]::uuid, 'candidates.documents.delete')
  and public.can_access_candidate(
    (storage.foldername(name))[2]::uuid,
    (storage.foldername(name))[1]::uuid
  )
);


-- Extend resource boundaries to candidate child records and operational records.
-- These tables contain candidate PII or recruitment activity and must not retain
-- organisation-wide member policies after the parent records become scoped.

drop policy if exists candidate_education_member_read on public.candidate_education;
create policy candidate_education_resource_read on public.candidate_education
for select to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'candidates.read')
  and public.can_access_candidate(candidate_id, organization_id));

drop policy if exists candidate_employment_member_read on public.candidate_employment_history;
create policy candidate_employment_resource_read on public.candidate_employment_history
for select to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'candidates.read')
  and public.can_access_candidate(candidate_id, organization_id));

drop policy if exists candidate_languages_member_read on public.candidate_languages;
create policy candidate_languages_resource_read on public.candidate_languages
for select to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'candidates.read')
  and public.can_access_candidate(candidate_id, organization_id));

drop policy if exists candidate_certifications_member_read on public.candidate_certifications;
create policy candidate_certifications_resource_read on public.candidate_certifications
for select to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'candidates.read')
  and public.can_access_candidate(candidate_id, organization_id));

drop policy if exists candidate_processing_member_read on public.candidate_processing_records;
create policy candidate_processing_resource_read on public.candidate_processing_records
for select to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'privacy.manage')
  and public.can_access_candidate(candidate_id, organization_id));

drop policy if exists candidate_tag_assignments_member_read on public.candidate_tag_assignments;
create policy candidate_tag_assignments_resource_read on public.candidate_tag_assignments
for select to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'candidates.read')
  and public.can_access_candidate(candidate_id, organization_id));

drop policy if exists talent_pool_memberships_member_read on public.talent_pool_memberships;
create policy talent_pool_memberships_resource_read on public.talent_pool_memberships
for select to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'candidates.read')
  and public.can_access_candidate(candidate_id, organization_id));

drop policy if exists talent_pool_membership_events_member_read on public.talent_pool_membership_events;
create policy talent_pool_membership_events_resource_read on public.talent_pool_membership_events
for select to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'candidates.read')
  and exists (
    select 1 from public.talent_pool_memberships tm
    where tm.id = talent_pool_membership_events.membership_id
      and tm.organization_id = talent_pool_membership_events.organization_id
      and public.can_access_candidate(tm.candidate_id, tm.organization_id)
  ));

drop policy if exists application_stage_history_member_read on public.application_stage_history;
create policy application_stage_history_resource_read on public.application_stage_history
for select to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'applications.read')
  and public.can_access_application(application_id, organization_id));

drop policy if exists application_stage_history_member_insert on public.application_stage_history;
create policy application_stage_history_resource_insert on public.application_stage_history
for insert to authenticated
with check (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'applications.update')
  and (actor_user_id is null or actor_user_id = auth.uid())
  and public.can_access_application(application_id, organization_id));

drop policy if exists recruiter_notes_member_select on public.recruiter_notes;
create policy recruiter_notes_resource_read on public.recruiter_notes
for select to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'candidates.read')
  and public.can_access_candidate(candidate_id, organization_id));

drop policy if exists recruiter_notes_member_insert on public.recruiter_notes;
create policy recruiter_notes_resource_insert on public.recruiter_notes
for insert to authenticated
with check (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'candidates.update')
  and author_user_id = auth.uid()
  and public.can_access_candidate(candidate_id, organization_id));

drop policy if exists recruiter_tasks_member_select on public.recruiter_tasks;
create policy recruiter_tasks_resource_read on public.recruiter_tasks
for select to authenticated
using (public.is_org_member(organization_id)
  and (
    (candidate_id is not null
      and public.has_effective_org_permission(organization_id, 'candidates.read')
      and public.can_access_candidate(candidate_id, organization_id))
    or (job_id is not null
      and public.has_effective_org_permission(organization_id, 'jobs.read')
      and public.can_access_job(job_id, organization_id))
    or (candidate_id is null and job_id is null
        and (assigned_to = auth.uid() or created_by = auth.uid()))
  ));

drop policy if exists recruiter_tasks_member_insert on public.recruiter_tasks;
create policy recruiter_tasks_resource_insert on public.recruiter_tasks
for insert to authenticated
with check (public.is_org_member(organization_id)
  and created_by = auth.uid()
  and (assigned_to is null or exists (
    select 1 from public.organization_members m
    where m.organization_id = recruiter_tasks.organization_id and m.user_id = recruiter_tasks.assigned_to
  ))
  and (candidate_id is null or public.can_access_candidate(candidate_id, organization_id))
  and (job_id is null or public.can_access_job(job_id, organization_id)));

drop policy if exists recruiter_tasks_member_update on public.recruiter_tasks;
create policy recruiter_tasks_resource_update on public.recruiter_tasks
for update to authenticated
using (public.is_org_member(organization_id)
  and (assigned_to = auth.uid() or created_by = auth.uid())
  and (candidate_id is null or public.can_access_candidate(candidate_id, organization_id))
  and (job_id is null or public.can_access_job(job_id, organization_id)))
with check (public.is_org_member(organization_id)
  and (assigned_to = auth.uid() or created_by = auth.uid())
  and (candidate_id is null or public.can_access_candidate(candidate_id, organization_id))
  and (job_id is null or public.can_access_job(job_id, organization_id)));

drop policy if exists recruiter_tasks_member_delete on public.recruiter_tasks;
create policy recruiter_tasks_resource_delete on public.recruiter_tasks
for delete to authenticated
using (public.is_org_member(organization_id)
  and created_by = auth.uid()
  and (candidate_id is null or public.can_access_candidate(candidate_id, organization_id))
  and (job_id is null or public.can_access_job(job_id, organization_id)));

drop policy if exists job_distribution_member_read on public.job_distribution_channels;
create policy job_distribution_resource_read on public.job_distribution_channels
for select to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'jobs.read')
  and public.can_access_job(job_id, organization_id));

drop policy if exists job_distribution_member_write on public.job_distribution_channels;
create policy job_distribution_resource_write on public.job_distribution_channels
for all to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'jobs.update')
  and public.can_access_job(job_id, organization_id))
with check (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'jobs.update')
  and public.can_access_job(job_id, organization_id));

-- Job requisitions are visible only to their requester/approver or users who
-- can access the linked client or resulting vacancy.
drop policy if exists job_requisitions_member_select on public.job_requisitions;
create policy job_requisitions_resource_read on public.job_requisitions
for select to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'jobs.read')
  and (
    requested_by = auth.uid()
    or approved_by = auth.uid()
    or rejected_by = auth.uid()
    or (client_id is not null and public.can_access_client(client_id, organization_id))
    or (job_id is not null and public.can_access_job(job_id, organization_id))
  ));

drop policy if exists job_requisitions_member_update on public.job_requisitions;
create policy job_requisitions_resource_update on public.job_requisitions
for update to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'jobs.update')
  and (
    requested_by = auth.uid()
    or (client_id is not null and public.can_access_client(client_id, organization_id))
    or (job_id is not null and public.can_access_job(job_id, organization_id))
  ))
with check (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'jobs.update')
  and (
    requested_by = auth.uid()
    or (client_id is not null and public.can_access_client(client_id, organization_id))
    or (job_id is not null and public.can_access_job(job_id, organization_id))
  ));


-- Additional sensitive records discovered in the staging RLS inventory.
-- AI interview material and JD history inherit the vacancy boundary.
drop policy if exists ai_interview_kits_member_read on public.ai_interview_kits;
create policy ai_interview_kits_resource_read on public.ai_interview_kits
for select to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'ai.use')
  and public.can_access_job(job_id, organization_id));

drop policy if exists ai_jd_versions_member_read on public.ai_job_description_versions;
create policy ai_jd_versions_resource_read on public.ai_job_description_versions
for select to authenticated
using (public.is_org_member(organization_id)
  and public.has_effective_org_permission(organization_id, 'ai.use')
  and public.can_access_job(job_id, organization_id));

drop policy if exists campaign_memberships_member_read on public.campaign_memberships;
create policy campaign_memberships_resource_read on public.campaign_memberships
for select to authenticated
using (public.is_org_member(organization_id)
  and (
    (candidate_id is not null and public.has_effective_org_permission(organization_id, 'candidates.read')
      and public.can_access_candidate(candidate_id, organization_id))
    or (application_id is not null and public.has_effective_org_permission(organization_id, 'applications.read')
      and public.can_access_application(application_id, organization_id))
  ));

drop policy if exists campaign_events_member_read on public.campaign_events;
create policy campaign_events_resource_read on public.campaign_events
for select to authenticated
using (public.is_org_member(organization_id)
  and (
    (candidate_id is not null and public.has_effective_org_permission(organization_id, 'candidates.read')
      and public.can_access_candidate(candidate_id, organization_id))
    or (application_id is not null and public.has_effective_org_permission(organization_id, 'applications.read')
      and public.can_access_application(application_id, organization_id))
  ));

drop policy if exists referrals_member_read on public.referrals;
create policy referrals_resource_read on public.referrals
for select to authenticated
using (public.is_org_member(organization_id)
  and (
    (candidate_id is not null and public.has_effective_org_permission(organization_id, 'candidates.read')
      and public.can_access_candidate(candidate_id, organization_id))
    or (application_id is not null and public.has_effective_org_permission(organization_id, 'applications.read')
      and public.can_access_application(application_id, organization_id))
  ));

-- Import result payloads can contain full CV-derived data. Keep them with the
-- batch uploader or organisation-wide administrators, and scope linked rows.
drop policy if exists import_batches_member_read on public.import_batches;
create policy import_batches_scoped_read on public.import_batches
for select to authenticated
using (public.is_org_member(organization_id)
  and (uploaded_by = auth.uid() or public.has_organization_wide_access(organization_id)));

drop policy if exists import_row_results_member_read on public.import_row_results;
create policy import_row_results_scoped_read on public.import_row_results
for select to authenticated
using (public.is_org_member(organization_id)
  and exists (
    select 1 from public.import_batches b
    where b.id = import_row_results.batch_id
      and b.organization_id = import_row_results.organization_id
      and (b.uploaded_by = auth.uid() or public.has_organization_wide_access(b.organization_id))
  )
  and (
    (candidate_id is null and duplicate_candidate_id is null)
    or (candidate_id is not null and public.can_access_candidate(candidate_id, organization_id))
    or (duplicate_candidate_id is not null and public.can_access_candidate(duplicate_candidate_id, organization_id))
  ));
