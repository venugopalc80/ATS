-- Candidate portal identity is tenant-scoped. No browser role receives table access.
-- The backend links an Auth user only after Supabase confirms the user's email.

alter table public.candidates
  add constraint candidates_org_id_id_unique unique (organization_id, id);

create table public.candidate_portal_accounts (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  candidate_id uuid not null,
  user_id uuid not null references auth.users(id) on delete cascade,
  linked_at timestamptz not null default now(),
  last_verified_at timestamptz not null default now(),
  constraint candidate_portal_accounts_candidate_fk
    foreign key (organization_id, candidate_id)
    references public.candidates (organization_id, id) on delete cascade,
  constraint candidate_portal_accounts_org_candidate_unique
    unique (organization_id, candidate_id),
  constraint candidate_portal_accounts_org_user_unique
    unique (organization_id, user_id)
);

create index candidate_portal_accounts_user_idx
  on public.candidate_portal_accounts (user_id);

alter table public.candidate_portal_accounts enable row level security;
revoke all on public.candidate_portal_accounts from anon, authenticated;
