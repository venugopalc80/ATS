-- Application pipeline stages and immutable stage history.
-- Status changes are captured in the database so every write path is auditable.
alter table public.applications
  drop constraint if exists applications_status_check;

alter table public.applications
  add constraint applications_status_check
  check (status in (
    'new', 'applied', 'screening', 'shortlisted', 'submitted',
    'interview', 'assessment', 'offer', 'hired', 'rejected', 'withdrawn'
  ));

create table if not exists public.application_stage_config (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  stage_key text not null check (stage_key in (
    'applied', 'screening', 'shortlisted', 'interview',
    'assessment', 'offer', 'hired', 'rejected', 'withdrawn'
  )),
  label text not null,
  display_order integer not null default 0,
  is_terminal boolean not null default false,
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, stage_key)
);

create index if not exists application_stage_config_org_order_idx
  on public.application_stage_config (organization_id, display_order);

insert into public.application_stage_config
  (organization_id, stage_key, label, display_order, is_terminal)
select o.id, s.stage_key, s.label, s.display_order, s.is_terminal
from public.organizations o
cross join (values
  ('applied', 'Applied', 10, false),
  ('screening', 'Screening', 20, false),
  ('shortlisted', 'Shortlisted', 30, false),
  ('interview', 'Interview', 40, false),
  ('assessment', 'Assessment', 50, false),
  ('offer', 'Offer', 60, false),
  ('hired', 'Hired', 70, true),
  ('rejected', 'Rejected', 80, true),
  ('withdrawn', 'Withdrawn', 90, true)
) as s(stage_key, label, display_order, is_terminal)
on conflict (organization_id, stage_key) do nothing;

create table if not exists public.application_stage_history (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  application_id uuid not null references public.applications(id) on delete cascade,
  previous_stage text,
  new_stage text not null,
  actor_user_id uuid references public.profiles(id) on delete set null,
  reason text,
  created_at timestamptz not null default now()
);

create index if not exists application_stage_history_app_created_idx
  on public.application_stage_history (organization_id, application_id, created_at desc);

alter table public.application_stage_config enable row level security;
alter table public.application_stage_history enable row level security;

drop policy if exists application_stage_config_member_all on public.application_stage_config;
create policy application_stage_config_member_all on public.application_stage_config
  for all using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));

drop policy if exists application_stage_history_member_read on public.application_stage_history;
create policy application_stage_history_member_read on public.application_stage_history
  for select using (public.is_org_member(organization_id));

create or replace function public.capture_application_stage_history()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  actor_id uuid;
  reason_text text;
begin
  if new.status is not distinct from old.status then
    return new;
  end if;

  begin
    actor_id := nullif(current_setting('app.actor_user_id', true), '')::uuid;
  exception when others then
    actor_id := null;
  end;

  reason_text := nullif(current_setting('app.application_transition_reason', true), '');

  insert into public.application_stage_history
    (organization_id, application_id, previous_stage, new_stage, actor_user_id, reason)
  values
    (new.organization_id, new.id, old.status, new.status, actor_id, reason_text);

  return new;
end;
$$;

drop trigger if exists applications_stage_history on public.applications;
create trigger applications_stage_history
  after update of status on public.applications
  for each row execute function public.capture_application_stage_history();

revoke all on function public.capture_application_stage_history() from public;
