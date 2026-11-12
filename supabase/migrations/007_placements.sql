-- Placement lifecycle records. Keep this migration before workflow audit triggers.
create table if not exists public.placements (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  application_id uuid not null references public.applications(id) on delete restrict,
  offer_id uuid references public.offers(id) on delete set null,
  job_id uuid not null references public.jobs(id) on delete restrict,
  candidate_id uuid not null references public.candidates(id) on delete restrict,
  client_id uuid references public.clients(id) on delete set null,
  status text not null default 'pending' check (status in ('pending','active','completed','cancelled')),
  start_date date not null,
  end_date date,
  fee_amount numeric,
  fee_currency text,
  fee_type text check (fee_type is null or fee_type in ('fixed','percentage')),
  fee_percentage numeric check (fee_percentage is null or (fee_percentage >= 0 and fee_percentage <= 100)),
  notes text,
  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (end_date is null or end_date >= start_date)
);

create index if not exists placements_org_status_idx on public.placements (organization_id, status);
create index if not exists placements_candidate_idx on public.placements (candidate_id);
create index if not exists placements_client_idx on public.placements (client_id);
create index if not exists placements_start_date_idx on public.placements (start_date);

alter table public.placements enable row level security;
drop policy if exists placements_member_all on public.placements;
create policy placements_member_all on public.placements
  for all using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));
