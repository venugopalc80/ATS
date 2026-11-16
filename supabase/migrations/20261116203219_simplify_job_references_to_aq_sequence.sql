create table if not exists private.job_reference_sequences (
    organization_id uuid primary key references public.organizations(id) on delete cascade,
    last_value bigint not null default 0 check (last_value >= 0)
);

revoke all on table private.job_reference_sequences from public, anon, authenticated;

drop trigger if exists jobs_assign_job_reference on public.jobs;
drop function if exists public.assign_job_reference();
drop index if exists public.jobs_organization_job_code_unique;

with numbered_jobs as (
    select
        id,
        row_number() over (partition by organization_id order by created_at, id) as sequence_value
    from public.jobs
)
update public.jobs as jobs
set job_code = 'AQ-' || case
    when numbered_jobs.sequence_value < 1000 then lpad(numbered_jobs.sequence_value::text, 3, '0')
    else numbered_jobs.sequence_value::text
end
from numbered_jobs
where jobs.id = numbered_jobs.id;

insert into private.job_reference_sequences (organization_id, last_value)
select organization_id, count(*)::bigint
from public.jobs
group by organization_id
on conflict (organization_id)
do update set last_value = excluded.last_value;

create unique index jobs_organization_job_code_unique
    on public.jobs (organization_id, job_code)
    where job_code is not null;

create or replace function public.assign_job_reference()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_sequence bigint;
begin
    if tg_op = 'UPDATE' then
        new.job_code := old.job_code;
        return new;
    end if;

    insert into private.job_reference_sequences (organization_id, last_value)
    values (new.organization_id, 1)
    on conflict (organization_id)
    do update set last_value = private.job_reference_sequences.last_value + 1
    returning last_value into v_sequence;

    new.job_code := 'AQ-' || case
        when v_sequence < 1000 then lpad(v_sequence::text, 3, '0')
        else v_sequence::text
    end;
    return new;
end;
$$;

revoke all on function public.assign_job_reference() from public, anon, authenticated;

create trigger jobs_assign_job_reference
before insert or update of job_code on public.jobs
for each row
execute function public.assign_job_reference();

comment on column public.jobs.job_code is
    'Automatically generated immutable AQ-### requisition reference, sequential per organisation.';
