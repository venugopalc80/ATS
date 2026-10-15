-- Attribute recruiter feedback without inventing authorship for historical records.
ALTER TABLE public.interviews
  ADD COLUMN IF NOT EXISTS feedback_author_id uuid REFERENCES public.profiles(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS feedback_at timestamptz;

COMMENT ON COLUMN public.interviews.feedback_author_id IS
  'Authenticated profile that last changed the interview feedback text.';
COMMENT ON COLUMN public.interviews.feedback_at IS
  'Timestamp when the current interview feedback text was last changed.';

-- Keep feedback audit events useful without copying the feedback text into a
-- second store. The application actor is set by the backend in the transaction.
CREATE OR REPLACE FUNCTION public.audit_interview_feedback_change()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  actor_text text;
  actor_id uuid;
BEGIN
  IF NEW.feedback IS DISTINCT FROM OLD.feedback THEN
    actor_text := current_setting('app.actor_user_id', true);
    IF actor_text IS NOT NULL AND actor_text <> '' THEN
      actor_id := actor_text::uuid;
    ELSE
      actor_id := NULL;
    END IF;

    INSERT INTO public.audit_events
      (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
    VALUES
      (NEW.organization_id, actor_id, 'interviews.feedback_changed', 'interview', NEW.id,
       jsonb_build_object(
         'feedback_present', NEW.feedback IS NOT NULL AND btrim(NEW.feedback) <> '',
         'feedback_at', NEW.feedback_at
       ));
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS interviews_feedback_audit ON public.interviews;
CREATE TRIGGER interviews_feedback_audit
AFTER UPDATE OF feedback ON public.interviews
FOR EACH ROW
EXECUTE FUNCTION public.audit_interview_feedback_change();

REVOKE ALL ON FUNCTION public.audit_interview_feedback_change() FROM PUBLIC;
