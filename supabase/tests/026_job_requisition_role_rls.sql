-- Disposable PostgreSQL integration test for migrations 024-026.
-- This harness creates a minimal Supabase-compatible auth/RLS environment.
\set ON_ERROR_STOP on

create extension if not exists pgcrypto;
create schema if not exists auth;
do $$ begin
  if not exists (select 1 from pg_roles where rolname='authenticated') then create role authenticated nologin; end if;
  if not exists (select 1 from pg_roles where rolname='anon') then create role anon nologin; end if;
end $$;
create or replace function auth.uid() returns uuid
language sql stable
as $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
grant usage on schema auth to authenticated, anon;
grant execute on function auth.uid() to authenticated, anon;

create table public.organizations (id uuid primary key, updated_at timestamptz not null default now());
create table public.profiles (id uuid primary key);
create table public.organization_members (
 organization_id uuid not null references public.organizations(id),
 user_id uuid not null references public.profiles(id),
 role text not null check (role in ('owner','admin','recruiter','hiring_manager','viewer')),
 primary key (organization_id,user_id)
);
create table public.clients (
 id uuid primary key,
 organization_id uuid not null references public.organizations(id)
);
create table public.jobs (
 id uuid primary key default gen_random_uuid(),
 organization_id uuid not null references public.organizations(id),
 job_code text,
 title text not null default 'Test job'
);
create or replace function public.is_org_member(p_org_id uuid) returns boolean
language sql stable security definer set search_path=public
as $$ select exists (
 select 1 from public.organization_members m
 where m.organization_id=p_org_id and m.user_id=auth.uid()
) $$;
grant usage on schema public to authenticated, anon;
grant select on public.organization_members, public.clients to authenticated;
grant execute on function public.is_org_member(uuid) to authenticated;

insert into public.organizations values
 ('10000000-0000-0000-0000-000000000001'),
 ('10000000-0000-0000-0000-000000000002');
insert into public.profiles values
 ('20000000-0000-0000-0000-000000000001'), -- recruiter
 ('20000000-0000-0000-0000-000000000002'), -- hiring manager
 ('20000000-0000-0000-0000-000000000003'), -- viewer
 ('20000000-0000-0000-0000-000000000004'), -- admin
 ('20000000-0000-0000-0000-000000000005'), -- other recruiter
 ('20000000-0000-0000-0000-000000000006'), -- foreign recruiter
 ('20000000-0000-0000-0000-000000000007'); -- foreign hiring manager
insert into public.organization_members values
 ('10000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000001','recruiter'),
 ('10000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000002','hiring_manager'),
 ('10000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000003','viewer'),
 ('10000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000004','admin'),
 ('10000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000005','recruiter'),
 ('10000000-0000-0000-0000-000000000002','20000000-0000-0000-0000-000000000006','recruiter'),
 ('10000000-0000-0000-0000-000000000002','20000000-0000-0000-0000-000000000007','hiring_manager');
insert into public.clients values
 ('30000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001'),
 ('30000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000002');

\i supabase/migrations/024_job_requisitions.sql
\i supabase/migrations/025_job_requisition_fk_indexes.sql
\i supabase/migrations/026_job_requisition_role_rls.sql
\i supabase/migrations/027_automatic_job_references.sql

-- Seed rows as the database owner; tests below run as authenticated.
insert into public.job_requisitions
 (id,organization_id,requisition_code,title,requested_by,justification,status)
values
 ('40000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001','REQ-SEED-1','Other recruiter draft','20000000-0000-0000-0000-000000000005','Seed row','draft'),
 ('40000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000001','REQ-SEED-2','Submitted recruiter request','20000000-0000-0000-0000-000000000001','Seed row','pending_approval'),
 ('40000000-0000-0000-0000-000000000003','10000000-0000-0000-0000-000000000001','REQ-SEED-3','Own recruiter draft','20000000-0000-0000-0000-000000000001','Seed row','draft');

set role authenticated;

-- Recruiter creates a requisition with valid assignees.
select set_config('request.jwt.claim.sub','20000000-0000-0000-0000-000000000001',false);
insert into public.job_requisitions
 (organization_id,requisition_code,title,requested_by,hiring_manager_id,recruiter_id,justification)
values
 ('10000000-0000-0000-0000-000000000001','REQ-TEST-RECRUITER','Recruiter created','20000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000002','20000000-0000-0000-0000-000000000001','Valid role creation');

-- Hiring manager can create.
select set_config('request.jwt.claim.sub','20000000-0000-0000-0000-000000000002',false);
insert into public.job_requisitions
 (organization_id,requisition_code,title,requested_by,justification)
values
 ('10000000-0000-0000-0000-000000000001','REQ-TEST-HM','Hiring manager created','20000000-0000-0000-0000-000000000002','Valid role creation');

-- Viewer, ineligible assignees, and cross-tenant references must be rejected.
select set_config('request.jwt.claim.sub','20000000-0000-0000-0000-000000000003',false);
do $$ begin
 begin
  insert into public.job_requisitions (organization_id,requisition_code,title,requested_by,justification)
  values ('10000000-0000-0000-0000-000000000001','REQ-BLOCK-VIEWER','Viewer','20000000-0000-0000-0000-000000000003','Must fail');
  raise exception 'viewer insert unexpectedly succeeded';
 exception when insufficient_privilege then null;
 end;
end $$;

select set_config('request.jwt.claim.sub','20000000-0000-0000-0000-000000000001',false);
do $$ begin
 begin
  insert into public.job_requisitions (organization_id,requisition_code,title,requested_by,hiring_manager_id,justification)
  values ('10000000-0000-0000-0000-000000000001','REQ-BLOCK-HM-ROLE','Bad HM','20000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000005','Must fail');
  raise exception 'ineligible hiring-manager assignment unexpectedly succeeded';
 exception when insufficient_privilege then null;
 end;
 begin
  insert into public.job_requisitions (organization_id,requisition_code,title,requested_by,recruiter_id,justification)
  values ('10000000-0000-0000-0000-000000000001','REQ-BLOCK-REC-ROLE','Bad recruiter','20000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000002','Must fail');
  raise exception 'ineligible recruiter assignment unexpectedly succeeded';
 exception when insufficient_privilege then null;
 end;
 begin
  insert into public.job_requisitions (organization_id,requisition_code,title,requested_by,client_id,justification)
  values ('10000000-0000-0000-0000-000000000001','REQ-BLOCK-CLIENT','Foreign client','20000000-0000-0000-0000-000000000001','30000000-0000-0000-0000-000000000002','Must fail');
  raise exception 'cross-organisation client unexpectedly succeeded';
 exception when insufficient_privilege then null;
 end;
 begin
  insert into public.job_requisitions (organization_id,requisition_code,title,requested_by,hiring_manager_id,justification)
  values ('10000000-0000-0000-0000-000000000001','REQ-BLOCK-FOREIGN-HM','Foreign HM','20000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000007','Must fail');
  raise exception 'cross-organisation assignee unexpectedly succeeded';
 exception when insufficient_privilege then null;
 end;
end $$;

-- A requester can edit their own draft, but not another requester's draft
-- or their own submitted request.
update public.job_requisitions set title='Own draft edited'
where id='40000000-0000-0000-0000-000000000003';
do $$ declare affected integer; begin
 update public.job_requisitions set title='Hijacked draft'
 where id='40000000-0000-0000-0000-000000000001';
 get diagnostics affected = row_count;
 if affected <> 0 then raise exception 'requester updated another user requisition'; end if;
 update public.job_requisitions set title='Submitted edit'
 where id='40000000-0000-0000-0000-000000000002';
 get diagnostics affected = row_count;
 if affected <> 0 then raise exception 'requester updated submitted requisition'; end if;
end $$;

-- UPDATE WITH CHECK must also reject invalid reassignment and tenant changes.
do $$ begin
 begin
  update public.job_requisitions
  set client_id='30000000-0000-0000-0000-000000000002'
  where id='40000000-0000-0000-0000-000000000003';
  raise exception 'requester assigned a cross-organisation client during update';
 exception when insufficient_privilege then null;
 end;
 begin
  update public.job_requisitions
  set hiring_manager_id='20000000-0000-0000-0000-000000000005'
  where id='40000000-0000-0000-0000-000000000003';
  raise exception 'requester assigned an ineligible hiring manager during update';
 exception when insufficient_privilege then null;
 end;
 begin
  update public.job_requisitions
  set recruiter_id='20000000-0000-0000-0000-000000000002'
  where id='40000000-0000-0000-0000-000000000003';
  raise exception 'requester assigned an ineligible recruiter during update';
 exception when insufficient_privilege then null;
 end;
 begin
  update public.job_requisitions
  set organization_id='10000000-0000-0000-0000-000000000002'
  where id='40000000-0000-0000-0000-000000000003';
  raise exception 'requester moved requisition to another organisation';
 exception when insufficient_privilege then null;
 end;
end $$;

-- Admin retains administrative update access.
select set_config('request.jwt.claim.sub','20000000-0000-0000-0000-000000000004',false);
update public.job_requisitions set title='Admin updated'
where id='40000000-0000-0000-0000-000000000001';

-- Lifecycle/approval columns remain unavailable to direct authenticated UPDATE.
do $$ begin
 begin
  update public.job_requisitions set status='approved'
  where id='40000000-0000-0000-0000-000000000001';
  raise exception 'authenticated user unexpectedly updated protected status column';
 exception when insufficient_privilege then null;
 end;
end $$;

reset role;

-- Job references are generated, tenant-scoped, unique and immutable.
insert into public.jobs (organization_id, title)
values ('10000000-0000-0000-0000-000000000001', 'First job'),
       ('10000000-0000-0000-0000-000000000001', 'Second job'),
       ('10000000-0000-0000-0000-000000000002', 'Other tenant job');

do $job_reference_test$
declare
  first_code text;
  second_code text;
  other_code text;
begin
  select job_code into first_code from public.jobs where title='First job';
  select job_code into second_code from public.jobs where title='Second job';
  select job_code into other_code from public.jobs where title='Other tenant job';
  if first_code <> 'JOB-001' or second_code <> 'JOB-002' then
    raise exception 'unexpected sequential job references: %, %', first_code, second_code;
  end if;
  if other_code <> 'JOB-001' then
    raise exception 'job references should be scoped to each organisation: %', other_code;
  end if;
  begin
    update public.jobs set job_code='MANUAL-999' where title='First job';
    raise exception 'job reference unexpectedly changed';
  exception when check_violation then null;
  end;
end;
$job_reference_test$;

select 'migration 024-027 RLS and job-reference checks passed' as result;
