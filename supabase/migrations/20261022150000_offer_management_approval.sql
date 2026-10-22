-- AQERITH Idea 12: Offer Management & Approval.
-- Additive, tenant-scoped migration. Apply to ATS-Staging only after review.
-- Production must not be changed as part of feature development.

create unique index if not exists offers_organization_id_id_uidx
  on public.offers (organization_id, id);

-- Keep legacy values readable while introducing the explicit offer lifecycle.
do $$
declare constraint_row record;
begin
  for constraint_row in
    select conname
    from pg_constraint
    where conrelid = 'public.offers'::regclass
      and contype = 'c'
      and pg_get_constraintdef(oid) ilike '%status%'
  loop
    execute format('alter table public.offers drop constraint %I', constraint_row.conname);
  end loop;
end $$;

alter table public.offers
  add constraint offers_status_check
  check (status in (
    'draft', 'awaiting_approval', 'approved', 'issued',
    'accepted', 'declined', 'expired', 'withdrawn',
    -- Backwards-compatible values for records created by the earlier offers workflow.
    'sent', 'rejected'
  ));

alter table public.offers
  add column if not exists current_version integer not null default 1,
  add column if not exists approved_at timestamptz,
  add column if not exists approved_by uuid references public.profiles(id) on delete set null,
  add column if not exists issued_at timestamptz,
  add column if not exists issued_by uuid references public.profiles(id) on delete set null,
  add column if not exists candidate_responded_at timestamptz,
  add column if not exists candidate_response text check (candidate_response is null or candidate_response in ('accepted','declined')),
  add column if not exists withdrawn_at timestamptz,
  add column if not exists withdrawn_by uuid references public.profiles(id) on delete set null;

create table if not exists public.offer_versions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  offer_id uuid not null,
  version_number integer not null check (version_number > 0),
  terms jsonb not null check (jsonb_typeof(terms) = 'object'),
  terms_sha256 text not null check (terms_sha256 ~ '^[a-f0-9]{64}$'),
  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  issued_at timestamptz,
  document_storage_path text,
  document_sha256 text check (document_sha256 is null or document_sha256 ~ '^[a-f0-9]{64}$'),
  unique (organization_id, id),
  unique (organization_id, offer_id, version_number),
  foreign key (organization_id, offer_id) references public.offers(organization_id, id) on delete cascade,
  check (document_storage_path is null or length(document_storage_path) <= 1000)
);

create table if not exists public.offer_approvals (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  offer_id uuid not null,
  offer_version_id uuid not null,
  approver_id uuid not null references public.profiles(id) on delete restrict,
  decision text not null check (decision in ('approved','rejected','changes_requested')),
  comments text,
  decided_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  unique (organization_id, id),
  foreign key (organization_id, offer_id) references public.offers(organization_id, id) on delete cascade,
  foreign key (organization_id, offer_version_id) references public.offer_versions(organization_id, id) on delete restrict,
  check (comments is null or length(comments) <= 4000)
);

create table if not exists public.offer_documents (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  offer_id uuid not null,
  offer_version_id uuid not null,
  document_type text not null check (document_type in ('offer_letter','signed_offer','supporting_document')),
  storage_path text not null check (length(trim(storage_path)) between 1 and 1000),
  content_type text not null default 'application/pdf',
  checksum_sha256 text check (checksum_sha256 is null or checksum_sha256 ~ '^[a-f0-9]{64}$'),
  uploaded_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  unique (organization_id, id),
  foreign key (organization_id, offer_id) references public.offers(organization_id, id) on delete cascade,
  foreign key (organization_id, offer_version_id) references public.offer_versions(organization_id, id) on delete restrict
);

create index if not exists offer_versions_offer_version_idx
  on public.offer_versions (organization_id, offer_id, version_number desc);
create index if not exists offer_approvals_offer_time_idx
  on public.offer_approvals (organization_id, offer_id, decided_at desc);
create index if not exists offer_approvals_approver_time_idx
  on public.offer_approvals (organization_id, approver_id, decided_at desc);
create index if not exists offer_documents_version_idx
  on public.offer_documents (organization_id, offer_version_id);

alter table public.offer_versions enable row level security;
alter table public.offer_approvals enable row level security;
alter table public.offer_documents enable row level security;

-- All access is mediated by the authenticated backend, which checks organisation
-- membership and role before reading or mutating offer records.
revoke all on public.offer_versions, public.offer_approvals, public.offer_documents
  from anon, authenticated;

create or replace function public.prevent_offer_version_mutation()
returns trigger
language plpgsql
set search_path = ''
as 'BEGIN RAISE EXCEPTION ''offer versions are immutable; create a new version''; END;';

drop trigger if exists offer_versions_immutable on public.offer_versions;
create trigger offer_versions_immutable
before update or delete on public.offer_versions
for each row execute function public.prevent_offer_version_mutation();

create or replace function public.prevent_offer_approval_mutation()
returns trigger
language plpgsql
set search_path = ''
as 'BEGIN RAISE EXCEPTION ''offer approval decisions are append-only''; END;';

drop trigger if exists offer_approvals_append_only on public.offer_approvals;
create trigger offer_approvals_append_only
before update or delete on public.offer_approvals
for each row execute function public.prevent_offer_approval_mutation();

comment on table public.offer_versions is 'Immutable snapshots of exact offer terms; edits create a new version.';
comment on table public.offer_approvals is 'Append-only approval decisions bound to the exact offer version reviewed.';
comment on table public.offer_documents is 'Private object-storage references; never expose storage paths or public URLs to candidates.';
comment on column public.offers.candidate_response is 'Candidate response only; distinct from employer approval and onboarding checks.';
