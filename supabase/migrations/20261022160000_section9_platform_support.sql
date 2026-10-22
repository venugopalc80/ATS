-- Section 9 / Idea 49: support operations foundations with tenant boundaries.
create table if not exists public.platform_operators (
  user_id uuid primary key references public.profiles(id) on delete cascade,
  active boolean not null default true,
  granted_by uuid references public.profiles(id) on delete set null,
  granted_at timestamptz not null default now(),
  notes text
);
alter table public.platform_operators enable row level security;
create policy platform_operators_deny_browser
  on public.platform_operators for all to anon, authenticated
  using (false) with check (false);
revoke all on public.platform_operators from anon, authenticated;

create table if not exists public.support_cases (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  created_by uuid not null references public.profiles(id) on delete restrict,
  assigned_operator_id uuid references public.platform_operators(user_id) on delete set null,
  category text not null check (category in ('billing','technical','account','security','privacy','other')),
  priority text not null default 'normal' check (priority in ('low','normal','high','urgent')),
  status text not null default 'open' check (status in ('open','in_progress','waiting_on_customer','resolved','closed')),
  subject text not null check (length(trim(subject)) between 4 and 180),
  description text not null check (length(trim(description)) between 10 and 8000),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  resolved_at timestamptz
);
create index if not exists support_cases_org_updated_idx
  on public.support_cases(organization_id, updated_at desc);
create index if not exists support_cases_status_priority_idx
  on public.support_cases(status, priority, created_at);
alter table public.support_cases enable row level security;
create policy support_cases_member_read
  on public.support_cases for select to authenticated
  using (public.is_org_member(organization_id));
revoke insert, update, delete on public.support_cases from anon, authenticated;
grant select on public.support_cases to authenticated;

create table if not exists public.support_case_messages (
  id uuid primary key default gen_random_uuid(),
  support_case_id uuid not null references public.support_cases(id) on delete cascade,
  author_user_id uuid references public.profiles(id) on delete set null,
  author_operator_id uuid references public.platform_operators(user_id) on delete set null,
  visibility text not null default 'customer' check (visibility in ('customer','internal')),
  body text not null check (length(trim(body)) between 1 and 8000),
  created_at timestamptz not null default now(),
  check ((author_user_id is null) <> (author_operator_id is null))
);
create index if not exists support_case_messages_case_created_idx
  on public.support_case_messages(support_case_id, created_at);
alter table public.support_case_messages enable row level security;
create policy support_case_messages_customer_read
  on public.support_case_messages for select to authenticated
  using (
    visibility = 'customer'
    and exists (
      select 1 from public.support_cases c
      where c.id = support_case_id and public.is_org_member(c.organization_id)
    )
  );
revoke insert, update, delete on public.support_case_messages from anon, authenticated;
grant select on public.support_case_messages to authenticated;

create table if not exists public.support_access_grants (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  operator_user_id uuid not null references public.platform_operators(user_id) on delete restrict,
  purpose text not null check (length(trim(purpose)) between 10 and 1000),
  scope text[] not null check (cardinality(scope) between 1 and 10),
  requested_at timestamptz not null default now(),
  approved_by_org_user_id uuid references public.profiles(id) on delete set null,
  approved_at timestamptz,
  expires_at timestamptz not null,
  revoked_at timestamptz,
  check (expires_at > requested_at),
  check ((approved_at is null) = (approved_by_org_user_id is null))
);
create index if not exists support_access_grants_org_expiry_idx
  on public.support_access_grants(organization_id, expires_at desc);
alter table public.support_access_grants enable row level security;
create policy support_access_grants_org_admin_read
  on public.support_access_grants for select to authenticated
  using (public.is_org_admin(organization_id));
revoke insert, update, delete on public.support_access_grants from anon, authenticated;
grant select on public.support_access_grants to authenticated;
