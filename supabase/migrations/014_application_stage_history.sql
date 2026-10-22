-- Idea 04: auditable application stage history.
-- Keep candidate profiles and per-job applications separate.

create table if not exists public.application_stage_history (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  application_id uuid not null references public.applications(id) on delete cascade,
  previous_stage text,
  new_stage text not null,
  actor_user_id uuid references public.profiles(id) on delete set null,
  reason text,
  created_at timestamptz not null default now(),
  constraint application_stage_history_reason_length
    check (reason is null or length(reason) <= 1000)
);

create index if not exists application_stage_history_org_application_created_idx
  on public.application_stage_history (organization_id, application_id, created_at desc);

alter table public.application_stage_history enable row level security;

drop policy if exists application_stage_history_member_read on public.application_stage_history;
create policy application_stage_history_member_read
  on public.application_stage_history for select
  using (public.is_org_member(organization_id));

drop policy if exists application_stage_history_member_insert on public.application_stage_history;
create policy application_stage_history_member_insert
  on public.application_stage_history for insert
  with check (
    public.is_org_member(organization_id)
    and (actor_user_id is null or actor_user_id = auth.uid())
  );

create or replace function public.record_application_stage_history()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  actor_id uuid;
  transition_reason text;
begin
  if tg_op = 'UPDATE' and new.status is not distinct from old.status then
    return new;
  end if;

  begin
    actor_id := nullif(current_setting('app.actor_user_id', true), '')::uuid;
  exception when others then
    actor_id := null;
  end;

  transition_reason := nullif(left(nullif(current_setting('app.transition_reason', true), ''), 1000), '');

  insert into public.application_stage_history
    (organization_id, application_id, previous_stage, new_stage, actor_user_id, reason, created_at)
  values (
    new.organization_id,
    new.id,
    case when tg_op = 'INSERT' then null else old.status end,
    new.status,
    actor_id,
    case when tg_op = 'INSERT' then coalesce(transition_reason, 'application_created') else transition_reason end,
    coalesce(new.updated_at, now())
  );

  return new;
end;
$$;

drop trigger if exists applications_stage_history_insert on public.applications;
create trigger applications_stage_history_insert
  after insert on public.applications
  for each row execute function public.record_application_stage_history();

drop trigger if exists applications_stage_history_update on public.applications;
create trigger applications_stage_history_update
  after update of status on public.applications
  for each row execute function public.record_application_stage_history();

-- Seed a baseline event for applications that existed before this migration.
insert into public.application_stage_history
  (organization_id, application_id, previous_stage, new_stage, actor_user_id, reason, created_at)
select a.organization_id, a.id, null, a.status, null, 'migration_baseline', a.created_at
from public.applications a
where not exists (
  select 1 from public.application_stage_history h where h.application_id = a.id
);

revoke all on function public.record_application_stage_history() from public, anon, authenticated;
