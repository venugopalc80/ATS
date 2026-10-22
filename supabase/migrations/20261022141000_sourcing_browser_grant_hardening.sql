-- Browser-role grant hardening for Section 4 tenant-owned sourcing tables.
-- Mutations must pass through FastAPI, which performs membership, ownership and audit checks.
revoke all on public.saved_searches, public.candidate_tags, public.candidate_tag_assignments,
  public.talent_pools, public.talent_pool_memberships, public.talent_pool_membership_events,
  public.candidate_sources, public.import_batches, public.import_row_results,
  public.recruitment_campaigns, public.campaign_channels, public.referrals,
  public.campaign_memberships, public.campaign_events from anon, authenticated;

grant select on public.saved_searches, public.candidate_tags, public.candidate_tag_assignments,
  public.talent_pools, public.talent_pool_memberships, public.talent_pool_membership_events,
  public.candidate_sources, public.import_batches, public.import_row_results,
  public.recruitment_campaigns, public.campaign_channels, public.referrals,
  public.campaign_memberships, public.campaign_events to authenticated;
