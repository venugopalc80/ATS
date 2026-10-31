-- Offer and placement writes must pass through authenticated backend lifecycle validation.
REVOKE ALL PRIVILEGES ON TABLE public.offers, public.placements FROM anon;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON TABLE public.offers, public.placements FROM authenticated;
GRANT SELECT ON TABLE public.offers, public.placements TO authenticated;
