-- Tighten direct authenticated access to requisitions.
-- The backend API enforces these rules already; mirror them in RLS so direct
-- Supabase clients cannot bypass requester and assignee role restrictions.

drop policy if exists job_requisitions_member_insert on public.job_requisitions;
create policy job_requisitions_member_insert on public.job_requisitions
 for insert to authenticated
 with check (
  (select public.is_org_member(organization_id))
  and requested_by = (select auth.uid())
  and exists (
   select 1 from public.organization_members requester
   where requester.organization_id = job_requisitions.organization_id
     and requester.user_id = (select auth.uid())
     and requester.role in ('owner','admin','hiring_manager','recruiter')
  )
  and (
   client_id is null or exists (
    select 1 from public.clients c
    where c.id = client_id and c.organization_id = job_requisitions.organization_id
   )
  )
  and (
   hiring_manager_id is null or exists (
    select 1 from public.organization_members assignee
    where assignee.organization_id = job_requisitions.organization_id
      and assignee.user_id = hiring_manager_id
      and assignee.role in ('owner','admin','hiring_manager')
   )
  )
  and (
   recruiter_id is null or exists (
    select 1 from public.organization_members assignee
    where assignee.organization_id = job_requisitions.organization_id
      and assignee.user_id = recruiter_id
      and assignee.role in ('owner','admin','recruiter')
   )
  )
 );

drop policy if exists job_requisitions_member_update on public.job_requisitions;
create policy job_requisitions_member_update on public.job_requisitions
 for update to authenticated
 using (
  (select public.is_org_member(organization_id))
  and exists (
   select 1 from public.organization_members requester
   where requester.organization_id = job_requisitions.organization_id
     and requester.user_id = (select auth.uid())
     and (
      requester.role in ('owner','admin')
      or (
       requester.role in ('hiring_manager','recruiter')
       and requested_by = (select auth.uid())
       and status in ('draft','rejected')
      )
     )
  )
 )
 with check (
  (select public.is_org_member(organization_id))
  and (
   client_id is null or exists (
    select 1 from public.clients c
    where c.id = client_id and c.organization_id = job_requisitions.organization_id
   )
  )
  and (
   hiring_manager_id is null or exists (
    select 1 from public.organization_members assignee
    where assignee.organization_id = job_requisitions.organization_id
      and assignee.user_id = hiring_manager_id
      and assignee.role in ('owner','admin','hiring_manager')
   )
  )
  and (
   recruiter_id is null or exists (
    select 1 from public.organization_members assignee
    where assignee.organization_id = job_requisitions.organization_id
      and assignee.user_id = recruiter_id
      and assignee.role in ('owner','admin','recruiter')
   )
  )
 );
