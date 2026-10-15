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

COMMENT ON TABLE public.rate_cards IS
  'Versioned organisation-scoped commercial rate terms. Writes must go through the authenticated backend API.';
