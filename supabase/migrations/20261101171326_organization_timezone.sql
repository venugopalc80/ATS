-- Organisation-level IANA timezone used for date-based recruitment reporting.
-- UTC is a safe default; organisations can configure their actual operating timezone.
ALTER TABLE public.organizations
  ADD COLUMN IF NOT EXISTS timezone text NOT NULL DEFAULT 'UTC';

ALTER TABLE public.organizations
  ADD CONSTRAINT organizations_timezone_not_blank
  CHECK (length(btrim(timezone)) > 0);
