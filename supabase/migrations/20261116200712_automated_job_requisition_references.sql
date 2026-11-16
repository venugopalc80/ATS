create table if not exists private.job_reference_counters (
    organization_id uuid not null references public.organizations(id) on delete cascade,
    reference_year integer not null check (reference_year between 2000 and 9999),
    last_value bigint not null default 0 check (last_value >= 0),
    primary key (organization_id, reference_year)
);

revoke all on table private.job_reference_counters from public, anon, authenticated;

with existing_max as (
    select
        organization_id,
        substring(job_code from 8 for 4)::integer as reference_year,
        max(substring(job_code from 13)::bigint) as last_value
    from public.jobs
    where job_code ~ '^AQ-JOB-[0-9]{4}-[0-9]{6}$'
    group by organization_id, substring(job_code from 8 for 4)::integer
),
missing_ranked as (
    select
        j.id,
        j.organization_id,
        extract(year from j.created_at)::integer as reference_year,
        coalesce(m.last_value, 0) +
            row_number() over (
                partition by j.organization_id, extract(year from j.created_at)::integer
                order by j.created_at, j.id
            ) as sequence_value
    from public.jobs j
    left join existing_max m
      on m.organization_id = j.organization_id
     and m.reference_year = extract(year from j.created_at)::integer
    where j.job_code is null or btrim(j.job_code) = ''
)
update public.jobs j
set job_code = 'AQ-JOB-' || r.reference_year::text || '-' || lpad(r.sequence_value::text, 6, '0')
from missing_ranked r
where j.id = r.id;

insert into private.job_reference_counters (organization_id, reference_year, last_value)
select
    organization_id,
    substring(job_code from 8 for 4)::integer,
    max(substring(job_code from 13)::bigint)
from public.jobs
where job_code ~ '^AQ-JOB-[0-9]{4}-[0-9]{6}$'
group by organization_id, substring(job_code from 8 for 4)::integer
on conflict (organization_id, reference_year)
do update set last_value = greatest(
    private.job_reference_counters.last_value,
    excluded.last_value
);

create unique index if not exists jobs_organization_job_code_unique
    on public.jobs (organization_id, job_code)
    where job_code is not null;

create or replace function public.assign_job_reference()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_year integer;
    v_sequence bigint;
begin
    if tg_op = 'UPDATE' then
        new.job_code := old.job_code;
        return new;
    end if;

    v_year := extract(year from coalesce(new.created_at, now()))::integer;

    insert into private.job_reference_counters (
        organization_id,
        reference_year,
        last_value
    )
    values (new.organization_id, v_year, 1)
    on conflict (organization_id, reference_year)
    do update
       set last_value = private.job_reference_counters.last_value + 1
    returning last_value into v_sequence;

    new.job_code := 'AQ-JOB-' || v_year::text || '-' || lpad(v_sequence::text, 6, '0');
    return new;
end;
$$;

revoke all on function public.assign_job_reference() from public, anon, authenticated;

drop trigger if exists jobs_assign_job_reference on public.jobs;
create trigger jobs_assign_job_reference
before insert or update of job_code on public.jobs
for each row
execute function public.assign_job_reference();

comment on column public.jobs.job_code is
    'Automatically generated, immutable requisition reference unique within an organisation.';
