-- AQERITH Engage: candidate communication history and scoped send permission.
insert into public.permission_catalog (permission_key, category, label, description, sensitive)
values ('candidates.communicate','candidate_communications','Communicate with candidates','Send and review candidate communications',true)
on conflict (permission_key) do update set
  category=excluded.category, label=excluded.label, description=excluded.description, sensitive=excluded.sensitive;

insert into public.organization_role_permissions (organization_id, role_id, permission_key, allowed)
select r.organization_id, r.id, 'candidates.communicate',
       case when r.role_key in ('owner','admin','recruiter','hiring_manager') then true else false end
from public.organization_roles r
on conflict (role_id, permission_key) do nothing;

create table if not exists public.candidate_communications (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  candidate_id uuid not null references public.candidates(id) on delete cascade,
  channel text not null check (channel in ('email','message')),
  direction text not null check (direction in ('outbound','inbound','internal')),
  subject text,
  body_text text not null,
  recipient_email text,
  sender_user_id uuid references public.profiles(id) on delete set null,
  provider text,
  provider_message_id text,
  delivery_status text not null default 'logged' check (delivery_status in ('draft','queued','sent','delivered','bounced','failed','received','logged')),
  template_key text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  foreign key (organization_id, candidate_id)
    references public.candidates(organization_id, id) on delete cascade
);

create index if not exists candidate_communications_candidate_created_idx
  on public.candidate_communications(organization_id, candidate_id, created_at desc);
create index if not exists candidate_communications_org_created_idx
  on public.candidate_communications(organization_id, created_at desc);

alter table public.candidate_communications enable row level security;
drop policy if exists candidate_communications_member_read on public.candidate_communications;
create policy candidate_communications_member_read
on public.candidate_communications for select to authenticated
using (public.is_org_member(organization_id));

revoke insert, update, delete on public.candidate_communications from anon, authenticated;
