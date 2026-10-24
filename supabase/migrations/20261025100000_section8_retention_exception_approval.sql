-- Require explicit, independent approval for retention exceptions.
-- Existing rows retain their historical approval state; creator identity is unknown
-- for legacy rows and is therefore intentionally left NULL.
alter table public.retention_exceptions
  add column if not exists created_by uuid references public.profiles(id) on delete set null;

alter table public.retention_exceptions
  drop constraint if exists retention_exception_approval_separation;

alter table public.retention_exceptions
  add constraint retention_exception_approval_separation
  check (approved_by is null or created_by is null or approved_by <> created_by);

create index if not exists retention_exceptions_org_approval_idx
  on public.retention_exceptions (organization_id, approved_by, created_at desc);
