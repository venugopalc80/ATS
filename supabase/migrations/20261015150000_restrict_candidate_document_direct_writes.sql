-- Candidate CV/document metadata is sensitive personal data.
-- Browser clients must not write document metadata directly; use the authenticated
-- backend workflow so tenant checks, file validation, and audit attribution stay
-- in one place. RLS remains enabled and no client-facing policies are added here.

REVOKE ALL PRIVILEGES ON TABLE public.candidate_documents FROM anon;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON TABLE public.candidate_documents FROM authenticated;
GRANT SELECT ON TABLE public.candidate_documents TO authenticated;
