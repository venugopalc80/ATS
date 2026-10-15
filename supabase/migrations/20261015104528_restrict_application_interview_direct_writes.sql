-- Keep application and interview writes behind the authenticated backend API.
-- Browser roles must not bypass workflow transition validation or audit actor handling.
REVOKE ALL PRIVILEGES ON TABLE public.applications, public.interviews FROM anon;

REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON TABLE public.applications, public.interviews
  FROM authenticated;

-- Read-only browser access remains tenant-filtered by the existing RLS policies.
GRANT SELECT ON TABLE public.applications, public.interviews TO authenticated;
