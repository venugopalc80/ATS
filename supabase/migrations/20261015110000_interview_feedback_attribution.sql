-- Attribute recruiter feedback without inventing authorship for historical records.
ALTER TABLE public.interviews
  ADD COLUMN IF NOT EXISTS feedback_author_id uuid REFERENCES public.profiles(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS feedback_at timestamptz;

COMMENT ON COLUMN public.interviews.feedback_author_id IS
  'Authenticated profile that last changed the interview feedback text.';
COMMENT ON COLUMN public.interviews.feedback_at IS
  'Timestamp when the current interview feedback text was last changed.';
