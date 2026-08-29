create extension if not exists pgcrypto;
create extension if not exists vector;

create table if not exists organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  country_code text not null check (country_code in ('GB','US','IN','AU')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  full_name text,
  email text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists organization_members (
  organization_id uuid not null references organizations(id) on delete cascade,
  user_id uuid not null references profiles(id) on delete cascade,
  role text not null default 'viewer' check (role in ('owner','admin','recruiter','hiring_manager','viewer')),
  created_at timestamptz not null default now(),
  primary key (organization_id, user_id)
);

create table if not exists clients (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  name text not null,
  website text,
  industry text,
  country_code text,
  contact_name text,
  contact_email text,
  contact_phone text,
  status text not null default 'active' check (status in ('prospect','active','inactive')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists jobs (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  client_id uuid references clients(id) on delete set null,
  job_code text,
  title text not null,
  description text,
  location text,
  country_code text check (country_code in ('GB','US','IN','AU')),
  employment_type text,
  work_mode text,
  salary_min numeric,
  salary_max numeric,
  salary_currency char(3),
  experience_min numeric,
  experience_max numeric,
  work_authorization text,
  required_skills text[] not null default '{}',
  preferred_skills text[] not null default '{}',
  status text not null default 'draft' check (status in ('draft','open','on_hold','closed','filled','cancelled')),
  recruiter_id uuid references profiles(id) on delete set null,
  hiring_manager_id uuid references profiles(id) on delete set null,
  opened_at timestamptz,
  closed_at timestamptz,
  created_by uuid references profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists jobs_org_status_idx on jobs(organization_id, status);
create index if not exists jobs_client_idx on jobs(client_id);

create table if not exists candidates (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  first_name text not null,
  last_name text,
  email text,
  phone text,
  city text,
  region text,
  country_code text check (country_code in ('GB','US','IN','AU')),
  status text not null default 'active' check (status in ('active','inactive','placed','do_not_contact')),
  current_title text,
  years_experience numeric,
  skills text[] not null default '{}',
  resume_path text,
  resume_text text,
  embedding vector(1536),
  ai_summary text,
  consent_recorded_at timestamptz,
  consent_purpose text,
  retention_until timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists candidates_org_status_idx on candidates(organization_id, status);

create table if not exists applications (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  job_id uuid not null references jobs(id) on delete cascade,
  candidate_id uuid not null references candidates(id) on delete cascade,
  source text,
  status text not null default 'new' check (status in ('new','screening','submitted','interview','offer','hired','rejected','withdrawn')),
  match_score numeric check (match_score is null or (match_score >= 0 and match_score <= 100)),
  match_explanation text,
  human_reviewed boolean not null default false,
  human_reviewed_by uuid references profiles(id) on delete set null,
  human_reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(job_id, candidate_id)
);

create index if not exists applications_org_status_idx on applications(organization_id, status);
create index if not exists applications_job_idx on applications(job_id);
create index if not exists applications_candidate_idx on applications(candidate_id);

create table if not exists audit_events (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  actor_user_id uuid references profiles(id) on delete set null,
  action text not null,
  entity_type text not null,
  entity_id uuid,
  metadata jsonb not null default '{}',
  created_at timestamptz not null default now()
);

create index if not exists audit_org_created_idx on audit_events(organization_id, created_at desc);

alter table organizations enable row level security;
alter table profiles enable row level security;
alter table organization_members enable row level security;
alter table clients enable row level security;
alter table jobs enable row level security;
alter table candidates enable row level security;
alter table applications enable row level security;
alter table audit_events enable row level security;

create or replace function public.is_org_member(target_org uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from organization_members m
    where m.organization_id = target_org and m.user_id = auth.uid()
  );
$$;

create policy organizations_member_read on organizations for select using (is_org_member(id));
create policy profiles_self_read on profiles for select using (id = auth.uid());
create policy memberships_member_read on organization_members for select using (user_id = auth.uid() or is_org_member(organization_id));
create policy clients_member_all on clients for all using (is_org_member(organization_id)) with check (is_org_member(organization_id));
create policy jobs_member_all on jobs for all using (is_org_member(organization_id)) with check (is_org_member(organization_id));
create policy candidates_member_all on candidates for all using (is_org_member(organization_id)) with check (is_org_member(organization_id));
create policy applications_member_all on applications for all using (is_org_member(organization_id)) with check (is_org_member(organization_id));
create policy audit_member_read on audit_events for select using (is_org_member(organization_id));
