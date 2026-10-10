create table if not exists public.job_distribution_channels (
  organization_id uuid not null references public.organizations(id) on delete cascade,
  job_id uuid not null references public.jobs(id) on delete cascade,
  channel_id text not null check (channel_id in ('careers','google','linkedin','indeed','monster','other')),
  selected boolean not null default false,
  status text not null check (status in ('not_selected','ready','needs_public_page','integration_required')),
  updated_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (job_id, channel_id)
);

create index if not exists job_distribution_org_job_idx
  on public.job_distribution_channels (organization_id, job_id);

alter table public.job_distribution_channels enable row level security;

create policy job_distribution_member_read
  on public.job_distribution_channels for select
  using (public.is_org_member(organization_id));

create policy job_distribution_member_write
  on public.job_distribution_channels for all
  using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));
