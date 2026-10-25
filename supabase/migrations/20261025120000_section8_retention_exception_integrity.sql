-- Enforce retention exception integrity at the database boundary as well as the API.
-- Staging was checked first: no existing rows violate either condition.
alter table public.retention_exceptions
  drop constraint if exists retention_exception_reason_not_blank;
alter table public.retention_exceptions
  add constraint retention_exception_reason_not_blank
  check (btrim(reason) <> '');

alter table public.retention_exceptions
  drop constraint if exists retention_exception_valid_window;
alter table public.retention_exceptions
  add constraint retention_exception_valid_window
  check (ends_at is null or ends_at > starts_at);
