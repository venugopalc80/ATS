-- Idea 13: versioned recruitment documents and provider-backed e-signature audit trail.
-- Content is stored in a private bucket. Each edit creates a new version row.

-- Parent-record composite keys make tenant ownership enforceable by the database.
-- These prerequisites are defined here because this migration sorts before later
-- timestamped feature migrations that also use composite tenant-safe references.
create unique index if not exists candidates_organization_id_id_uidx
  on public.candidates (organization_id, id);
create unique index if not exists applications_organization_id_id_uidx
  on public.applications (organization_id, id);
create unique index if not exists offers_organization_id_id_uidx
  on public.offers (organization_id, id);

create table if not exists public.recruitment_document_templates (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  name text not null check (length(trim(name)) between 2 and 160),
  document_type text not null check (document_type in ('offer_letter','acknowledgement','policy','other')),
  jurisdiction_code text not null check (jurisdiction_code in ('GB','US','IN','AU','GLOBAL')),
  current_version integer not null default 1 check (current_version > 0),
  active boolean not null default true,
  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, organization_id)
);
create index if not exists recruitment_templates_org_active_idx
  on public.recruitment_document_templates (organization_id, active, name);

create table if not exists public.recruitment_document_template_versions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  template_id uuid not null,
  version integer not null check (version > 0),
  body text not null check (length(body) <= 500000),
  placeholders jsonb not null default '[]'::jsonb check (jsonb_typeof(placeholders) = 'array'),
  content_sha256 text not null check (content_sha256 ~ '^[a-f0-9]{64}$'),
  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  foreign key (template_id, organization_id)
    references public.recruitment_document_templates(id, organization_id) on delete cascade,
  unique (template_id, version),
  unique (id, organization_id)
);

create table if not exists public.recruitment_documents (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  document_group_id uuid not null default gen_random_uuid(),
  version integer not null default 1 check (version > 0),
  template_version_id uuid,
  candidate_id uuid,
  application_id uuid,
  offer_id uuid,
  document_type text not null check (document_type in ('offer_letter','acknowledgement','policy','other')),
  jurisdiction_code text not null check (jurisdiction_code in ('GB','US','IN','AU','GLOBAL')),
  status text not null default 'draft'
    check (status in ('draft','generated','sent','viewed','signed','declined','expired','revoked','void')),
  storage_bucket text not null default 'recruitment-documents',
  storage_path text not null unique,
  file_name text not null,
  content_type text not null check (content_type in ('application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document')),
  file_size_bytes bigint not null check (file_size_bytes > 0 and file_size_bytes <= 20971520),
  content_sha256 text not null check (content_sha256 ~ '^[a-f0-9]{64}$'),
  generated_from_template_version integer,
  sent_at timestamptz,
  viewed_at timestamptz,
  signed_at timestamptz,
  declined_at timestamptz,
  expires_at timestamptz,
  revoked_at timestamptz,
  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (template_version_id, organization_id)
    references public.recruitment_document_template_versions(id, organization_id) on delete restrict,
  foreign key (organization_id, candidate_id)
    references public.candidates(organization_id, id) on delete restrict,
  foreign key (organization_id, application_id)
    references public.applications(organization_id, id) on delete restrict,
  foreign key (organization_id, offer_id)
    references public.offers(organization_id, id) on delete restrict,
  unique (document_group_id, version),
  check (candidate_id is not null or application_id is not null or offer_id is not null),
  unique (id, organization_id)
);
create index if not exists recruitment_documents_org_status_idx
  on public.recruitment_documents (organization_id, status, created_at desc);
create index if not exists recruitment_documents_offer_idx
  on public.recruitment_documents (organization_id, offer_id, created_at desc);
create index if not exists recruitment_documents_application_idx
  on public.recruitment_documents (organization_id, application_id, created_at desc);

create table if not exists public.recruitment_document_signers (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  document_id uuid not null,
  signer_reference text,
  signer_role text not null check (signer_role in ('candidate','employer','witness','other')),
  email text not null,
  status text not null default 'pending'
    check (status in ('pending','sent','viewed','signed','declined','expired','revoked')),
  sent_at timestamptz,
  viewed_at timestamptz,
  signed_at timestamptz,
  declined_at timestamptz,
  created_at timestamptz not null default now(),
  foreign key (document_id, organization_id)
    references public.recruitment_documents(id, organization_id) on delete cascade,
  unique (id, organization_id),
  unique (document_id, signer_role, email)
);
create index if not exists recruitment_signers_document_idx
  on public.recruitment_document_signers (organization_id, document_id, status);

-- Store verified provider event metadata; do not persist signing secrets or unnecessary full payloads.
create table if not exists public.recruitment_signature_events (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  document_id uuid,
  signer_id uuid,
  provider text not null check (length(trim(provider)) between 2 and 80),
  provider_event_id text not null,
  event_type text not null,
  provider_event_at timestamptz,
  received_at timestamptz not null default now(),
  payload_sha256 text not null check (payload_sha256 ~ '^[a-f0-9]{64}$'),
  verification_method text not null,
  foreign key (document_id, organization_id)
    references public.recruitment_documents(id, organization_id) on delete restrict,
  foreign key (signer_id, organization_id)
    references public.recruitment_document_signers(id, organization_id) on delete restrict,
  unique (provider, provider_event_id)
);
create index if not exists recruitment_signature_events_doc_idx
  on public.recruitment_signature_events (organization_id, document_id, received_at desc);

create table if not exists public.recruitment_document_access_events (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  document_id uuid not null,
  actor_user_id uuid references public.profiles(id) on delete set null,
  action text not null check (action in ('preview','download','link_created','link_revoked')),
  created_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb,
  foreign key (document_id, organization_id)
    references public.recruitment_documents(id, organization_id) on delete restrict
);
create index if not exists recruitment_document_access_doc_idx
  on public.recruitment_document_access_events (organization_id, document_id, created_at desc);

-- Content-addressed versions are immutable. New bytes must be stored as a new version.
create or replace function public.prevent_recruitment_document_content_rewrite()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if tg_op = 'DELETE' then
    -- Permit parent-organization cascades while blocking direct version deletion.
    if pg_trigger_depth() = 1 then
      raise exception 'Recruitment document versions cannot be deleted; revoke or supersede them';
    end if;
    return old;
  end if;
  if new.organization_id is distinct from old.organization_id
     or new.document_group_id is distinct from old.document_group_id
     or new.version is distinct from old.version
     or new.template_version_id is distinct from old.template_version_id
     or new.storage_bucket is distinct from old.storage_bucket
     or new.storage_path is distinct from old.storage_path
     or new.file_name is distinct from old.file_name
     or new.content_type is distinct from old.content_type
     or new.file_size_bytes is distinct from old.file_size_bytes
     or new.content_sha256 is distinct from old.content_sha256
     or new.generated_from_template_version is distinct from old.generated_from_template_version then
    raise exception 'Recruitment document content is immutable; create a new version';
  end if;
  if old.status = 'signed' and new.status is distinct from old.status then
    raise exception 'Signed document status is immutable';
  end if;
  return new;
end;
$$;
drop trigger if exists recruitment_documents_immutable_content on public.recruitment_documents;
create trigger recruitment_documents_immutable_content
before update or delete on public.recruitment_documents
for each row execute function public.prevent_recruitment_document_content_rewrite();

create or replace function public.prevent_recruitment_template_version_rewrite()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  -- Permit parent-organization/template cascades while blocking direct edits/deletes.
  if tg_op = 'DELETE' and pg_trigger_depth() > 1 then
    return old;
  end if;
  raise exception 'Recruitment template versions are immutable; create a new version';
end;
$$;
drop trigger if exists recruitment_template_versions_immutable on public.recruitment_document_template_versions;
create trigger recruitment_template_versions_immutable
before update or delete on public.recruitment_document_template_versions
for each row execute function public.prevent_recruitment_template_version_rewrite();

-- RLS is defense in depth; application APIs also verify membership and parent-record tenancy.
alter table public.recruitment_document_templates enable row level security;
alter table public.recruitment_document_template_versions enable row level security;
alter table public.recruitment_documents enable row level security;
alter table public.recruitment_document_signers enable row level security;
alter table public.recruitment_signature_events enable row level security;
alter table public.recruitment_document_access_events enable row level security;

create policy recruitment_templates_member_read on public.recruitment_document_templates
  for select using (public.is_org_member(organization_id));
create policy recruitment_template_versions_member_read on public.recruitment_document_template_versions
  for select using (public.is_org_member(organization_id));
create policy recruitment_documents_member_read on public.recruitment_documents
  for select using (public.is_org_member(organization_id));
create policy recruitment_signers_member_read on public.recruitment_document_signers
  for select using (public.is_org_member(organization_id));
create policy recruitment_signature_events_member_read on public.recruitment_signature_events
  for select using (public.is_org_member(organization_id));
create policy recruitment_access_events_member_read on public.recruitment_document_access_events
  for select using (public.is_org_member(organization_id));

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('recruitment-documents','recruitment-documents',false,20971520,
  array['application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document'])
on conflict (id) do update set public=false, file_size_limit=20971520,
  allowed_mime_types=excluded.allowed_mime_types;
