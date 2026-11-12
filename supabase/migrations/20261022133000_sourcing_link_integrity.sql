-- Follow-up integrity guard: a referral's application must belong to the same candidate and organisation.
create or replace function public.validate_aqerith_sourcing_links()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if tg_table_name = 'candidate_tag_assignments' then
    if not exists (select 1 from public.candidates c where c.id = new.candidate_id and c.organization_id = new.organization_id) then
      raise exception 'Tagged candidate must belong to the same organisation' using errcode = '23514';
    end if;
  elsif tg_table_name = 'talent_pool_memberships' then
    if not exists (select 1 from public.candidates c where c.id = new.candidate_id and c.organization_id = new.organization_id) then
      raise exception 'Candidate must belong to the same organisation' using errcode = '23514';
    end if;
  elsif tg_table_name = 'recruitment_campaigns' then
    if new.target_job_id is not null and not exists (select 1 from public.jobs j where j.id = new.target_job_id and j.organization_id = new.organization_id) then
      raise exception 'Target job must belong to the same organisation' using errcode = '23514';
    end if;
  elsif tg_table_name = 'referrals' then
    if new.candidate_id is not null and not exists (select 1 from public.candidates c where c.id = new.candidate_id and c.organization_id = new.organization_id) then
      raise exception 'Referral candidate must belong to the same organisation' using errcode = '23514';
    end if;
    if new.application_id is not null and not exists (
      select 1 from public.applications a
      where a.id = new.application_id and a.organization_id = new.organization_id
        and (new.candidate_id is null or a.candidate_id = new.candidate_id)
    ) then
      raise exception 'Referral application must match the candidate and organisation' using errcode = '23514';
    end if;
  elsif tg_table_name = 'campaign_memberships' then
    if not exists (select 1 from public.candidates c where c.id = new.candidate_id and c.organization_id = new.organization_id) then
      raise exception 'Campaign candidate must belong to the same organisation' using errcode = '23514';
    end if;
    if new.application_id is not null and not exists (select 1 from public.applications a where a.id = new.application_id and a.organization_id = new.organization_id and a.candidate_id = new.candidate_id) then
      raise exception 'Campaign application must match the candidate and organisation' using errcode = '23514';
    end if;
  elsif tg_table_name = 'import_row_results' then
    if new.candidate_id is not null and not exists (select 1 from public.candidates c where c.id = new.candidate_id and c.organization_id = new.organization_id) then
      raise exception 'Imported candidate must belong to the same organisation' using errcode = '23514';
    end if;
    if new.duplicate_candidate_id is not null and not exists (select 1 from public.candidates c where c.id = new.duplicate_candidate_id and c.organization_id = new.organization_id) then
      raise exception 'Duplicate candidate must belong to the same organisation' using errcode = '23514';
    end if;
  end if;
  return new;
end;
$$;
revoke all on function public.validate_aqerith_sourcing_links() from public;
