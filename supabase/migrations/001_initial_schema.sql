create extension if not exists pgcrypto;
create extension if not exists vector;

create type public.membership_role as enum ('owner','admin','recruiter','hiring_manager','viewer');
create type public.job_status as enum ('draft','open','on_hold','closed','filled','cancelled');
create type public.candidate_status as enum ('active','inactive','placed','do_not_contact');
create type public.application_status as enum ('new','screening','submitted','interview','offer','hired','rejected','withdrawn');

create table public.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  country_code text not null check (country_code in ('GB','US','IN','AU')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  full_name text,
  email text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.organization_members (
  organization_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid not null references public.profiles(id) on delete cascade,
  role public.membership_role not null default 'viewer',
  created_at timestamptz not null default now(),
  primary key (organization_id, user_id)
);

create table public.clients (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  name text not null,
  website text,
  industry text,
  country_code text,
  status text not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.jobs (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  client_id uuid references public.clients(id) on delete set null,
  job_code text,
  title text not null,
  description text,
  location text,
  country_code text check (country_code in ('GB','US','IN','AU')),
  employment_type text,
  salary_min numeric,
  salary_max numeric,
  salary_currency char(3),
  experience_min numeric,
  experience_max numeric,
  work_authorization text,
  required_skills text[] not null default '{}',
  preferred_skills text[] not null default '{}',
  status public.job_status not null default 'draft',
  recruiter_id uuid references public.profiles(id) on delete set null,
  hiring_manager_id uuid references public.profiles(id) on delete set null,
  opened_at timestamptz,
  closed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.candidates (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  first_name text not null,
  last_name text,
  email text,
  phone text,
  city text,
  region text,
  country_code text check (country_code in ('GB','US','IN','AU')),
  status public.candidate_status not null default 'active',
  years_experience numeric,
  skills text[] not null default '{}',
  resume_path text,
  resume_text text,
  embedding vector(1536),
  consent_recorded_at timestamptz,
  consent_purpose text,
  retention_until timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.applications (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  job_id uuid not null references public.jobs(id) on delete cascade,
  candidate_id uuid not null references public.candidates(id) on delete cascade,
  source text,
  status public.application_status not null default 'new',
  match_score numeric check (match_score is null or (match_score >= 0 and match_score <= 100)),
  match_explanation text,
  human_reviewed boolean not null default false,
  human_reviewed_by uuid references public.profiles(id) on delete set null,
  human_reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (job_id, candidate_id)
);

create table public.audit_events (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  actor_user_id uuid references public.profiles(id) on delete set null,
  entity_type text not null,
  entity_id uuid,
  action text not null,
  metadata jsonb not null default '{}',
  created_at timestamptz not null default now()
);

create index jobs_org_status_idx on public.jobs(organization_id, status);
create index candidates_org_status_idx on public.candidates(organization_id, status);
create index applications_org_status_idx on public.applications(organization_id, status);
create index applications_job_idx on public.applications(job_id);
create index audit_events_org_created_idx on public.audit_events(organization_id, created_at desc);

alter table public.organizations enable row level security;
alter table public.profiles enable row level security;
alter table public.organization_members enable row level security;
alter table public.clients enable row level security;
alter table public.jobs enable row level security;
alter table public.candidates enable row level security;
alter table public.applications enable row level security;
alter table public.audit_events enable row level security;

create or replace function public.is_org_member(target_org uuid)
returns boolean language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.organization_members m
    where m.organization_id = target_org and m.user_id = auth.uid()
  );
$$;

create policy "members can read organizations" on public.organizations for select using (public.is_org_member(id));
create policy "users can read own profile" on public.profiles for select using (id = auth.uid());
create policy "members can read memberships" on public.organization_members for select using (user_id = auth.uid() or public.is_org_member(organization_id));
create policy "members can access clients" on public.clients for all using (public.is_org_member(organization_id)) with check (public.is_org_member(organization_id));
create policy "members can access jobs" on public.jobs for all using (public.is_org_member(organization_id)) with check (public.is_org_member(organization_id));
create policy "members can access candidates" on public.candidates for all using (public.is_org_member(organization_id)) with check (public.is_org_member(organization_id));
create policy "members can access applications" on public.applications for all using (public.is_org_member(organization_id)) with check (public.is_org_member(organization_id));
create policy "members can read audit events" on public.audit_events for select using (public.is_org_member(organization_id));
