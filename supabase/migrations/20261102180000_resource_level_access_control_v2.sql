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
        and public.can_access_job(a.job_id, target_org, target_user)
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
          or public.can_access_candidate(a.candidate_id, target_org, target_user)
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

do $$
declare t text;
begin
  foreach t in array array[
    'organization_member_access_scopes','recruitment_teams','recruitment_team_members',
    'recruitment_team_jobs','recruitment_team_clients','candidate_access_assignments',
    'client_access_assignments'
  ] loop
    execute format('revoke all on public.%I from anon, authenticated', t);
  end loop;
end $$;

grant select on public.organization_member_access_scopes, public.recruitment_teams,
  public.recruitment_team_members, public.recruitment_team_jobs,
  public.recruitment_team_clients, public.candidate_access_assignments,
  public.client_access_assignments to authenticated;

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
