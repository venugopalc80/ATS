-- Sensitive sourcing records are accessed through FastAPI only.
-- The API applies recruiter-role checks, ownership rules, row-level visibility rules and audit logging.
-- Keep RLS enabled as defence in depth, but do not grant browser roles direct table access.
revoke all on public.saved_searches, public.candidate_tags, public.candidate_tag_assignments,
  public.talent_pools, public.talent_pool_memberships, public.talent_pool_membership_events,
  public.candidate_sources, public.import_batches, public.import_row_results,
  public.recruitment_campaigns, public.campaign_channels, public.referrals,
  public.campaign_memberships, public.campaign_events from anon, authenticated;
