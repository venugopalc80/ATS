CREATE TABLE IF NOT EXISTS public.rate_cards (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
  client_id uuid NOT NULL REFERENCES public.clients(id) ON DELETE RESTRICT,
  job_id uuid REFERENCES public.jobs(id) ON DELETE SET NULL,
  name text NOT NULL CHECK (char_length(btrim(name)) BETWEEN 2 AND 200),
  employment_type text NOT NULL CHECK (employment_type IN ('permanent','contract','temporary')),
  rate_basis text NOT NULL CHECK (rate_basis IN ('hourly','daily','annual_salary','fixed_fee','percentage_fee')),
  currency char(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
  rate_amount numeric(14,2),
  fee_percentage numeric(5,2),
  effective_from date NOT NULL,
  effective_to date,
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','active','expired','archived')),
  version integer NOT NULL DEFAULT 1 CHECK (version > 0),
  notes text,
  created_by uuid REFERENCES public.profiles(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (effective_to IS NULL OR effective_to >= effective_from),
  CHECK (
    (rate_basis = 'percentage_fee' AND fee_percentage IS NOT NULL AND fee_percentage > 0 AND fee_percentage <= 100 AND rate_amount IS NULL)
    OR
    (rate_basis <> 'percentage_fee' AND rate_amount IS NOT NULL AND rate_amount >= 0 AND fee_percentage IS NULL)
  )
);

CREATE INDEX IF NOT EXISTS rate_cards_org_client_idx
  ON public.rate_cards (organization_id, client_id, status);
CREATE INDEX IF NOT EXISTS rate_cards_job_idx
  ON public.rate_cards (organization_id, job_id);
CREATE INDEX IF NOT EXISTS rate_cards_effective_idx
  ON public.rate_cards (organization_id, effective_from, effective_to);

ALTER TABLE public.rate_cards ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rate_cards_member_read ON public.rate_cards;
CREATE POLICY rate_cards_member_read ON public.rate_cards
  FOR SELECT USING (public.is_org_member(organization_id));

REVOKE ALL PRIVILEGES ON TABLE public.rate_cards FROM anon;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON TABLE public.rate_cards FROM authenticated;
GRANT SELECT ON TABLE public.rate_cards TO authenticated;

-- Audit only commercial fields; do not duplicate free-text notes into audit logs.
CREATE OR REPLACE FUNCTION public.audit_rate_card_change()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  actor_text text;
  actor_id uuid;
  old_terms jsonb := '{}'::jsonb;
  new_terms jsonb := '{}'::jsonb;
  org_id uuid;
  card_id uuid;
  action_name text;
BEGIN
  actor_text := current_setting('app.actor_user_id', true);
  IF actor_text IS NOT NULL AND actor_text <> '' THEN
    actor_id := actor_text::uuid;
  ELSE
    actor_id := NULL;
  END IF;

  IF TG_OP = 'DELETE' THEN
    org_id := OLD.organization_id;
    card_id := OLD.id;
    action_name := 'rate_card.deleted';
    old_terms := jsonb_build_object(
      'client_id', OLD.client_id, 'job_id', OLD.job_id, 'name', OLD.name,
      'employment_type', OLD.employment_type, 'rate_basis', OLD.rate_basis,
      'currency', OLD.currency, 'rate_amount', OLD.rate_amount,
      'fee_percentage', OLD.fee_percentage, 'effective_from', OLD.effective_from,
      'effective_to', OLD.effective_to, 'status', OLD.status, 'version', OLD.version
    );
  ELSE
    org_id := NEW.organization_id;
    card_id := NEW.id;
    action_name := CASE WHEN TG_OP = 'INSERT' THEN 'rate_card.created' ELSE 'rate_card.updated' END;
    new_terms := jsonb_build_object(
      'client_id', NEW.client_id, 'job_id', NEW.job_id, 'name', NEW.name,
      'employment_type', NEW.employment_type, 'rate_basis', NEW.rate_basis,
      'currency', NEW.currency, 'rate_amount', NEW.rate_amount,
      'fee_percentage', NEW.fee_percentage, 'effective_from', NEW.effective_from,
      'effective_to', NEW.effective_to, 'status', NEW.status, 'version', NEW.version
    );
    IF TG_OP = 'UPDATE' THEN
      old_terms := jsonb_build_object(
        'client_id', OLD.client_id, 'job_id', OLD.job_id, 'name', OLD.name,
        'employment_type', OLD.employment_type, 'rate_basis', OLD.rate_basis,
        'currency', OLD.currency, 'rate_amount', OLD.rate_amount,
        'fee_percentage', OLD.fee_percentage, 'effective_from', OLD.effective_from,
        'effective_to', OLD.effective_to, 'status', OLD.status, 'version', OLD.version
      );
      IF old_terms = new_terms THEN RETURN NEW; END IF;
    END IF;
  END IF;

  INSERT INTO public.audit_events
    (organization_id, actor_user_id, action, entity_type, entity_id, metadata)
  VALUES
    (org_id, actor_id, action_name, 'rate_card', card_id,
     jsonb_build_object('old_terms', old_terms, 'new_terms', new_terms));

  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS rate_cards_audit ON public.rate_cards;
CREATE TRIGGER rate_cards_audit
AFTER INSERT OR UPDATE OR DELETE ON public.rate_cards
FOR EACH ROW EXECUTE FUNCTION public.audit_rate_card_change();

REVOKE ALL ON FUNCTION public.audit_rate_card_change() FROM PUBLIC;

COMMENT ON TABLE public.rate_cards IS
  'Versioned organisation-scoped commercial rate terms. Writes must go through the authenticated backend API.';
