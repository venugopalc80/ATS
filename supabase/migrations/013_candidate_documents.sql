-- Private CV documents are stored in Supabase Storage; only metadata lives in Postgres.
create table if not exists public.candidate_documents (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  candidate_id uuid not null references public.candidates(id) on delete cascade,
  application_id uuid references public.applications(id) on delete set null,
  document_type text not null default 'cv' check (document_type in ('cv','cover_letter','portfolio','other')),
  original_filename text not null,
  storage_bucket text not null default 'candidate-documents',
  storage_path text not null unique,
  content_type text not null check (content_type in ('application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document')),
  file_size_bytes bigint not null check (file_size_bytes > 0 and file_size_bytes <= 5242880),
  sha256 text not null,
  uploaded_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  deleted_at timestamptz
);
create index if not exists candidate_documents_org_candidate_created_idx
  on public.candidate_documents (organization_id, candidate_id, created_at desc)
  where deleted_at is null;
alter table public.candidate_documents enable row level security;
create policy candidate_documents_member_read on public.candidate_documents
  for select using (public.is_org_member(organization_id));
create policy candidate_documents_member_insert on public.candidate_documents
  for insert with check (public.is_org_member(organization_id) and uploaded_by = auth.uid());
create policy candidate_documents_member_update on public.candidate_documents
  for update using (public.is_org_member(organization_id)) with check (public.is_org_member(organization_id));
-- Bucket is private. The API uses service credentials only after checking user and tenant membership.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('candidate-documents', 'candidate-documents', false, 5242880,
  array['application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document'])
on conflict (id) do update set public = false, file_size_limit = 5242880,
  allowed_mime_types = excluded.allowed_mime_types;
