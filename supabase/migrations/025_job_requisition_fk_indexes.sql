create index if not exists job_requisitions_client_id_idx on public.job_requisitions (client_id);
create index if not exists job_requisitions_requested_by_idx on public.job_requisitions (requested_by);
create index if not exists job_requisitions_hiring_manager_id_idx on public.job_requisitions (hiring_manager_id);
create index if not exists job_requisitions_recruiter_id_idx on public.job_requisitions (recruiter_id);
create index if not exists job_requisitions_approved_by_idx on public.job_requisitions (approved_by);
create index if not exists job_requisitions_rejected_by_idx on public.job_requisitions (rejected_by);

drop policy if exists job_requisitions_member_select on public.job_requisitions;
create policy job_requisitions_member_select on public.job_requisitions
 for select to authenticated
 using ((select public.is_org_member(organization_id)));

drop policy if exists job_requisitions_member_insert on public.job_requisitions;
create policy job_requisitions_member_insert on public.job_requisitions
 for insert to authenticated
 with check (
  (select public.is_org_member(organization_id))
  and requested_by = (select auth.uid())
  and (client_id is null or exists (select 1 from public.clients c where c.id=client_id and c.organization_id=job_requisitions.organization_id))
  and (hiring_manager_id is null or exists (select 1 from public.organization_members m where m.organization_id=job_requisitions.organization_id and m.user_id=hiring_manager_id))
  and (recruiter_id is null or exists (select 1 from public.organization_members m where m.organization_id=job_requisitions.organization_id and m.user_id=recruiter_id))
 );

drop policy if exists job_requisitions_member_update on public.job_requisitions;
create policy job_requisitions_member_update on public.job_requisitions
 for update to authenticated
 using ((select public.is_org_member(organization_id)))
 with check (
  (select public.is_org_member(organization_id))
  and (client_id is null or exists (select 1 from public.clients c where c.id=client_id and c.organization_id=job_requisitions.organization_id))
  and (hiring_manager_id is null or exists (select 1 from public.organization_members m where m.organization_id=job_requisitions.organization_id and m.user_id=hiring_manager_id))
  and (recruiter_id is null or exists (select 1 from public.organization_members m where m.organization_id=job_requisitions.organization_id and m.user_id=recruiter_id))
 );
