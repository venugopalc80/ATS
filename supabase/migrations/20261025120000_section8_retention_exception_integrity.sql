-- Keep retention-exception integrity constraints safe to apply to environments
-- where the equivalent constraints were already added during staging validation.
do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'retention_exception_approval_separation'
          and conrelid = 'public.retention_exceptions'::regclass
    ) then
        alter table public.retention_exceptions
            add constraint retention_exception_approval_separation
            check (approved_by is null or created_by is null or approved_by <> created_by);
    end if;

    if not exists (
        select 1
        from pg_constraint
        where conname = 'retention_exception_reason_not_blank'
          and conrelid = 'public.retention_exceptions'::regclass
    ) then
        alter table public.retention_exceptions
            add constraint retention_exception_reason_not_blank
            check (btrim(reason) <> '');
    end if;

    if not exists (
        select 1
        from pg_constraint
        where conname = 'retention_exception_valid_window'
          and conrelid = 'public.retention_exceptions'::regclass
    ) then
        alter table public.retention_exceptions
            add constraint retention_exception_valid_window
            check (ends_at is null or ends_at > starts_at);
    end if;
end
$$;
