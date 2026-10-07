create table if not exists public.recruiter_notes (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  candidate_id uuid not null references public.candidates(id) on delete cascade,
  author_user_id uuid references public.profiles(id) on delete set null,
  note text not null check (length(trim(note)) > 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists recruiter_notes_org_candidate_created_idx on public.recruiter_notes (organization_id,candidate_id,created_at desc);
alter table public.recruiter_notes enable row level security;
create policy recruiter_notes_member_select on public.recruiter_notes for select to authenticated using (exists (select 1 from public.organization_members m where m.organization_id=recruiter_notes.organization_id and m.user_id=auth.uid()));
create policy recruiter_notes_member_insert on public.recruiter_notes for insert to authenticated with check (exists (select 1 from public.organization_members m where m.organization_id=recruiter_notes.organization_id and m.user_id=auth.uid()));
create policy recruiter_notes_member_update on public.recruiter_notes for update to authenticated using (exists (select 1 from public.organization_members m where m.organization_id=recruiter_notes.organization_id and m.user_id=auth.uid())) with check (exists (select 1 from public.organization_members m where m.organization_id=recruiter_notes.organization_id and m.user_id=auth.uid()));
create policy recruiter_notes_member_delete on public.recruiter_notes for delete to authenticated using (exists (select 1 from public.organization_members m where m.organization_id=recruiter_notes.organization_id and m.user_id=auth.uid()));