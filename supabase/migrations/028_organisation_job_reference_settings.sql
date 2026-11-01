-- 028: derive tenant job-reference defaults and support safe prefix configuration.
-- Existing job codes are never rewritten. The counter is only moved forward when
-- the derived prefix already has issued numeric references for that organisation.

with derived as (
  select
    id,
    case
      when left(regexp_replace(upper(name), '[^A-Z0-9]', '', 'g'), 1) between 'A' and 'Z'
       and length(left(regexp_replace(upper(name), '[^A-Z0-9]', '', 'g'), 3)) >= 2
      then left(regexp_replace(upper(name), '[^A-Z0-9]', '', 'g'), 3)
      else 'JOB'
    end as prefix
  from public.organizations
)
update public.organizations o
   set job_reference_prefix = d.prefix,
       job_reference_next_number = greatest(
         o.job_reference_next_number,
         coalesce((
           select max(substring(j.job_code from length(d.prefix) + 2)::bigint) + 1
             from public.jobs j
            where j.organization_id = o.id
              and j.job_code ~ ('^' || d.prefix || '-[0-9]+$')
         ), 1)
       )
  from derived d
 where d.id = o.id
   and o.job_reference_prefix = 'JOB';

comment on column public.organizations.job_reference_prefix is
  'Organisation-specific prefix for new automatically generated job references. Changing it never rewrites existing references.';
