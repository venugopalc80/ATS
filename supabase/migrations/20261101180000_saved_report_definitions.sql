create table if not exists public.saved_report_definitions (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete cascade,
    created_by uuid not null references public.profiles(id) on delete cascade,
    name text not null check (length(btrim(name)) between 1 and 100),
    description text check (description is null or length(description) <= 500),
    report_type text not null check (
        report_type in ('kpis', 'funnel', 'workload', 'sources', 'forecast', 'campaign_roi')
    ),
    filters jsonb not null default '{}'::jsonb check (jsonb_typeof(filters) = 'object'),
    is_shared boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists saved_report_definitions_org_updated_idx
    on public.saved_report_definitions (organization_id, updated_at desc);

create index if not exists saved_report_definitions_owner_name_idx
    on public.saved_report_definitions (organization_id, created_by, lower(name));

alter table public.saved_report_definitions enable row level security;

drop policy if exists saved_report_definitions_select on public.saved_report_definitions;
create policy saved_report_definitions_select
    on public.saved_report_definitions
    for select to authenticated
    using (
        public.is_org_member(organization_id)
        and (is_shared = true or created_by = auth.uid() or public.is_org_admin(organization_id))
    );

drop policy if exists saved_report_definitions_insert on public.saved_report_definitions;
create policy saved_report_definitions_insert
    on public.saved_report_definitions
    for insert to authenticated
    with check (
        created_by = auth.uid()
        and public.is_org_member(organization_id)
        and is_shared = false
    );

drop policy if exists saved_report_definitions_update_private on public.saved_report_definitions;
create policy saved_report_definitions_update_private
    on public.saved_report_definitions
    for update to authenticated
    using (
        created_by = auth.uid()
        and is_shared = false
        and public.is_org_member(organization_id)
    )
    with check (
        created_by = auth.uid()
        and is_shared = false
        and public.is_org_member(organization_id)
    );

drop policy if exists saved_report_definitions_update_admin on public.saved_report_definitions;
create policy saved_report_definitions_update_admin
    on public.saved_report_definitions
    for update to authenticated
    using (
        public.is_org_admin(organization_id)
    )
    with check (
        public.is_org_admin(organization_id)
    );

drop policy if exists saved_report_definitions_delete_private on public.saved_report_definitions;
create policy saved_report_definitions_delete_private
    on public.saved_report_definitions
    for delete to authenticated
    using (
        created_by = auth.uid()
        and is_shared = false
        and public.is_org_member(organization_id)
    );

drop policy if exists saved_report_definitions_delete_admin on public.saved_report_definitions;
create policy saved_report_definitions_delete_admin
    on public.saved_report_definitions
    for delete to authenticated
    using (
        public.is_org_admin(organization_id)
    );

grant select, insert, update, delete on public.saved_report_definitions to authenticated;
