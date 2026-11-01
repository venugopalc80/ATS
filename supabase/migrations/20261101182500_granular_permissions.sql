-- AQERITH reusable organisation-scoped permission foundation.
-- DRAFT RELEASE MIGRATION: apply to staging only after backend integration and review.
-- Direct PostgreSQL backend access means API authorization remains mandatory.

begin;

create table if not exists public.organization_permissions (
    permission_key text primary key,
    module text not null,
    description text not null,
    created_at timestamptz not null default now(),
    constraint organization_permissions_key_format
        check (permission_key ~ '^[a-z][a-z0-9_]*([.][a-z][a-z0-9_]*)+$')
);

insert into public.organization_permissions (permission_key, module, description)
values
 ('candidate.read_basic','candidates','View basic candidate profile fields'),
 ('candidate.read_contact','candidates','View candidate contact information'),
 ('candidate.create','candidates','Create candidate records'),
 ('candidate.update','candidates','Update candidate records'),
 ('candidate.archive','candidates','Archive and restore candidate records'),
 ('candidate.delete','candidates','Permanently delete candidate records'),
 ('candidate.export','candidates','Export candidate information'),
 ('candidate.cv.read','candidates','View candidate document listings'),
 ('candidate.cv.preview','candidates','Preview candidate documents'),
 ('candidate.cv.download','candidates','Download candidate documents'),
 ('candidate.cv.upload','candidates','Upload candidate documents'),
 ('candidate.cv.delete','candidates','Delete candidate documents'),
 ('candidate.notes.read','candidates','Read recruiter notes'),
 ('candidate.notes.create','candidates','Create recruiter notes'),
 ('application.read','applications','View application records'),
 ('application.manage','applications','Create and update application records'),
 ('application.delete','applications','Delete application records'),
 ('interview.read','interviews','View interview details'),
 ('interview.manage','interviews','Create and update interview records'),
 ('offer.read','offers','View offer details excluding protected compensation fields'),
 ('offer.manage','offers','Create and update offer records'),
 ('offer.salary.read','offers','View salary and compensation fields'),
 ('offer.salary.manage','offers','Create and update salary and compensation fields'),
 ('placement.read','placements','View placement records'),
 ('placement.manage','placements','Create and update placement records'),
 ('placement.fee.read','placements','View placement fee and commission fields'),
 ('placement.fee.manage','placements','Create and update placement fee and commission fields'),
 ('job.read','jobs','View job records'),
 ('job.manage','jobs','Create and update job records'),
 ('job.delete','jobs','Delete job records'),
 ('dashboard.read','dashboard','View organisation dashboard metrics'),
 ('client.read','clients','View client records'),
 ('client.manage','clients','Create and update client records'),
 ('client.delete','clients','Delete client records'),
 ('audit.read','administration','View organisation audit events'),
 ('member.read','administration','View organisation members')
on conflict (permission_key) do update
set module=excluded.module, description=excluded.description;

create table if not exists public.member_permission_grants (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null,
    user_id uuid not null,
    permission_key text not null references public.organization_permissions(permission_key)
        on update cascade on delete restrict,
    granted_by uuid not null references public.profiles(id) on delete restrict,
    granted_at timestamptz not null default now(),
    revoked_by uuid references public.profiles(id) on delete restrict,
    revoked_at timestamptz,
    revocation_reason text,
    constraint member_permission_grants_member_fk
        foreign key (organization_id,user_id)
        references public.organization_members(organization_id,user_id) on delete cascade,
    constraint member_permission_grants_revocation_pair
        check ((revoked_at is null and revoked_by is null)
            or (revoked_at is not null and revoked_by is not null)),
    constraint member_permission_grants_revocation_reason
        check (revocation_reason is null or length(btrim(revocation_reason)) between 1 and 500)
);

create unique index if not exists member_permission_grants_active_unique
 on public.member_permission_grants(organization_id,user_id,permission_key)
 where revoked_at is null;
create index if not exists member_permission_grants_member_active_idx
 on public.member_permission_grants(organization_id,user_id,permission_key)
 where revoked_at is null;
create index if not exists member_permission_grants_org_recent_idx
 on public.member_permission_grants(organization_id,granted_at desc);

alter table public.organization_permissions enable row level security;
alter table public.member_permission_grants enable row level security;
revoke all on public.organization_permissions from public, anon, authenticated;
revoke all on public.member_permission_grants from public, anon, authenticated;

comment on table public.organization_permissions is
 'Controlled catalogue of AQERITH organisation-level permissions.';
comment on table public.member_permission_grants is
 'Grant and revocation history for member permissions; backend enforces owner/admin authority.';

commit;
