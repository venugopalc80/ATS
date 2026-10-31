-- Enforce candidate/organisation consistency at the database layer.
-- Candidate IDs are globally unique today; the composite key makes tenant
-- ownership explicit for child tables and prevents mismatched organisation IDs.
create unique index if not exists candidates_id_organization_id_uidx
  on public.candidates (id, organization_id);

alter table public.candidate_education
  drop constraint if exists candidate_education_candidate_id_fkey;

alter table public.candidate_education
  add constraint candidate_education_candidate_org_fkey
  foreign key (candidate_id, organization_id)
  references public.candidates (id, organization_id)
  on delete cascade;
