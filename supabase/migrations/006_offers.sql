create table if not exists public.offers (
 id uuid primary key default gen_random_uuid(), organization_id uuid not null references public.organizations(id) on delete cascade,
 application_id uuid not null references public.applications(id) on delete cascade, title text not null,
 status text not null default 'draft' check (status in ('draft','sent','accepted','rejected','withdrawn','expired')),
 employment_type text, start_date date, salary_amount numeric(14,2), salary_currency text, bonus_amount numeric(14,2),
 benefits text, expires_at timestamptz, notes text, sent_at timestamptz, responded_at timestamptz,
 created_by uuid references public.profiles(id) on delete set null, created_at timestamptz not null default now(), updated_at timestamptz not null default now());
create index if not exists offers_org_status_idx on public.offers(organization_id,status);
create index if not exists offers_application_idx on public.offers(application_id);
alter table public.offers enable row level security;
drop policy if exists offers_member_all on public.offers;
create policy offers_member_all on public.offers for all using (public.is_org_member(organization_id)) with check (public.is_org_member(organization_id));