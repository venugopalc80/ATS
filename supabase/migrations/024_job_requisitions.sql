create table if not exists public.job_requisitions (
 id uuid primary key default gen_random_uuid(),
 organization_id uuid not null references public.organizations(id) on delete cascade,
 requisition_code text not null,
 title text not null check (length(trim(title)) between 1 and 200),
 department text,
 client_id uuid references public.clients(id) on delete set null,
 requested_by uuid not null references public.profiles(id) on delete restrict,
 hiring_manager_id uuid references public.profiles(id) on delete set null,
 recruiter_id uuid references public.profiles(id) on delete set null,
 headcount integer not null default 1 check (headcount > 0),
 justification text not null check (length(trim(justification)) > 0),
 budget_min numeric check (budget_min is null or budget_min >= 0),
 budget_max numeric check (budget_max is null or budget_max >= 0),
 location text,
 country_code text check (country_code is null or country_code in ('GB','US','IN','AU')),
 employment_type text,
 work_mode text,
 salary_min numeric check (salary_min is null or salary_min >= 0),
 salary_max numeric check (salary_max is null or salary_max >= 0),
 salary_currency char(3),
 required_skills text[] not null default '{}',
 target_start_date date,
 target_close_date date,
 status text not null default 'draft' check (status in ('draft','pending_approval','approved','rejected','converted','cancelled')),
 submitted_at timestamptz,
 approved_by uuid references public.profiles(id) on delete set null,
 approved_at timestamptz,
 rejected_by uuid references public.profiles(id) on delete set null,
 rejected_at timestamptz,
 rejection_reason text,
 approval_comment text,
 job_id uuid unique references public.jobs(id) on delete restrict,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 unique (organization_id, requisition_code),
 check (budget_min is null or budget_max is null or budget_max >= budget_min),
 check (salary_min is null or salary_max is null or salary_max >= salary_min),
 check ((status not in ('approved','converted')) or approved_at is not null),
 check (status <> 'converted' or job_id is not null)
);
create index if not exists job_requisitions_org_status_created_idx on public.job_requisitions (organization_id,status,created_at desc);
create index if not exists job_requisitions_org_requester_idx on public.job_requisitions (organization_id,requested_by,status);
create index if not exists job_requisitions_org_recruiter_idx on public.job_requisitions (organization_id,recruiter_id,status);
alter table public.job_requisitions enable row level security;
create policy job_requisitions_member_select on public.job_requisitions for select to authenticated using (public.is_org_member(organization_id));
create policy job_requisitions_member_insert on public.job_requisitions for insert to authenticated with check (
 public.is_org_member(organization_id) and requested_by = auth.uid()
 and (client_id is null or exists (select 1 from public.clients c where c.id=client_id and c.organization_id=job_requisitions.organization_id))
 and (hiring_manager_id is null or exists (select 1 from public.organization_members m where m.organization_id=job_requisitions.organization_id and m.user_id=hiring_manager_id))
 and (recruiter_id is null or exists (select 1 from public.organization_members m where m.organization_id=job_requisitions.organization_id and m.user_id=recruiter_id))
);
create policy job_requisitions_member_update on public.job_requisitions for update to authenticated using (public.is_org_member(organization_id)) with check (
 public.is_org_member(organization_id)
 and (client_id is null or exists (select 1 from public.clients c where c.id=client_id and c.organization_id=job_requisitions.organization_id))
 and (hiring_manager_id is null or exists (select 1 from public.organization_members m where m.organization_id=job_requisitions.organization_id and m.user_id=hiring_manager_id))
 and (recruiter_id is null or exists (select 1 from public.organization_members m where m.organization_id=job_requisitions.organization_id and m.user_id=recruiter_id))
);
revoke all on table public.job_requisitions from anon,authenticated;
grant select on table public.job_requisitions to authenticated;
grant insert (organization_id,requisition_code,title,department,client_id,requested_by,hiring_manager_id,recruiter_id,headcount,justification,budget_min,budget_max,location,country_code,employment_type,work_mode,salary_min,salary_max,salary_currency,required_skills,target_start_date,target_close_date) on public.job_requisitions to authenticated;
grant update (title,department,client_id,hiring_manager_id,recruiter_id,headcount,justification,budget_min,budget_max,location,country_code,employment_type,work_mode,salary_min,salary_max,salary_currency,required_skills,target_start_date,target_close_date) on public.job_requisitions to authenticated;
