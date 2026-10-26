-- Idea 04: organisation-configurable application stages.
-- Existing "new" status is presented as the Applied stage for backward compatibility.

alter table public.applications
  drop constraint if exists applications_status_check;

alter table public.applications
  add constraint applications_status_check
  check (status in (
    'new', 'screening', 'shortlisted', 'submitted', 'interview',
    'assessment', 'offer', 'hired', 'rejected', 'withdrawn'
  ));

create table if not exists public.application_stage_config (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  stage_key text not null check (stage_key in (
    'new', 'screening', 'shortlisted', 'submitted', 'interview',
    'assessment', 'offer', 'hired', 'rejected', 'withdrawn'
  )),
  label text not null check (length(trim(label)) between 1 and 80),
  display_order integer not null default 0 check (display_order >= 0),
  allowed_next_stages text[] not null default '{}'::text[],
  is_terminal boolean not null default false,
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, stage_key),
  check (not (is_terminal and cardinality(allowed_next_stages) > 0))
);

create index if not exists application_stage_config_org_order_idx
  on public.application_stage_config (organization_id, display_order, stage_key);

alter table public.application_stage_config enable row level security;
revoke all on public.application_stage_config from public, anon, authenticated;
drop policy if exists application_stage_config_member_read on public.application_stage_config;
create policy application_stage_config_member_read
  on public.application_stage_config for select
  using (public.is_org_member(organization_id));

insert into public.application_stage_config
  (organization_id, stage_key, label, display_order, allowed_next_stages, is_terminal)
select o.id, s.stage_key, s.label, s.display_order, s.allowed_next_stages, s.is_terminal
from public.organizations o
cross join (values
  ('new',        'Applied',     10, array['screening','rejected','withdrawn']::text[], false),
  ('screening',  'Screening',   20, array['shortlisted','submitted','interview','assessment','rejected','withdrawn']::text[], false),
  ('shortlisted','Shortlisted', 30, array['interview','assessment','rejected','withdrawn']::text[], false),
  ('submitted',  'Submitted',   35, array['interview','assessment','rejected','withdrawn']::text[], false),
  ('interview',  'Interview',   40, array['assessment','offer','rejected','withdrawn']::text[], false),
  ('assessment', 'Assessment',  50, array['interview','offer','rejected','withdrawn']::text[], false),
  ('offer',      'Offer',       60, array['hired','rejected','withdrawn']::text[], false),
  ('hired',      'Hired',       70, '{}'::text[], true),
  ('rejected',   'Rejected',   80, '{}'::text[], true),
  ('withdrawn',  'Withdrawn',  90, '{}'::text[], true)
) as s(stage_key, label, display_order, allowed_next_stages, is_terminal)
on conflict (organization_id, stage_key) do nothing;

create or replace function private.seed_default_application_stage_config()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.application_stage_config
    (organization_id, stage_key, label, display_order, allowed_next_stages, is_terminal)
  values
    (new.id, 'new', 'Applied', 10, array['screening','rejected','withdrawn']::text[], false),
    (new.id, 'screening', 'Screening', 20, array['shortlisted','submitted','interview','assessment','rejected','withdrawn']::text[], false),
    (new.id, 'shortlisted', 'Shortlisted', 30, array['interview','assessment','rejected','withdrawn']::text[], false),
    (new.id, 'submitted', 'Submitted', 35, array['interview','assessment','rejected','withdrawn']::text[], false),
    (new.id, 'interview', 'Interview', 40, array['assessment','offer','rejected','withdrawn']::text[], false),
    (new.id, 'assessment', 'Assessment', 50, array['interview','offer','rejected','withdrawn']::text[], false),
    (new.id, 'offer', 'Offer', 60, array['hired','rejected','withdrawn']::text[], false),
    (new.id, 'hired', 'Hired', 70, '{}'::text[], true),
    (new.id, 'rejected', 'Rejected', 80, '{}'::text[], true),
    (new.id, 'withdrawn', 'Withdrawn', 90, '{}'::text[], true)
  on conflict (organization_id, stage_key) do nothing;
  return new;
end;
$$;

drop trigger if exists organizations_seed_application_stage_config on public.organizations;
create trigger organizations_seed_application_stage_config
  after insert on public.organizations
  for each row execute function private.seed_default_application_stage_config();

revoke all on function private.seed_default_application_stage_config() from public, anon, authenticated;
