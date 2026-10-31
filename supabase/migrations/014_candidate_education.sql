-- Structured education records extracted from candidate CVs.
-- Keep raw_text so recruiters can correct imperfect heuristic parsing later.
create table if not exists public.candidate_education (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  candidate_id uuid not null references public.candidates(id) on delete cascade,
  institution text,
  qualification text,
  field_of_study text,
  start_year integer check (start_year is null or start_year between 1900 and 2100),
  graduation_year integer check (graduation_year is null or graduation_year between 1900 and 2100),
  raw_text text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (length(btrim(raw_text)) > 0),
  check (start_year is null or graduation_year is null or start_year <= graduation_year)
);

create index if not exists candidate_education_org_candidate_idx
  on public.candidate_education (organization_id, candidate_id, graduation_year desc);

alter table public.candidate_education enable row level security;

create policy candidate_education_member_read on public.candidate_education
  for select using (public.is_org_member(organization_id));
create policy candidate_education_member_insert on public.candidate_education
  for insert with check (
    public.is_org_member(organization_id)
    and exists (
      select 1 from public.candidates c
      where c.id = candidate_id and c.organization_id = candidate_education.organization_id
    )
  );
create policy candidate_education_member_update on public.candidate_education
  for update using (public.is_org_member(organization_id))
  with check (
    public.is_org_member(organization_id)
    and exists (
      select 1 from public.candidates c
      where c.id = candidate_id and c.organization_id = candidate_education.organization_id
    )
  );
create policy candidate_education_member_delete on public.candidate_education
  for delete using (public.is_org_member(organization_id));
