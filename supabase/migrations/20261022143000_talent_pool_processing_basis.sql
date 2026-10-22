-- Record a documented processing basis for each new talent-pool membership.
-- Existing memberships remain nullable for compatibility and must be reviewed before migration to production.
alter table public.talent_pool_memberships
  add column if not exists processing_basis text;
alter table public.talent_pool_memberships
  drop constraint if exists talent_pool_memberships_processing_basis_check;
alter table public.talent_pool_memberships
  add constraint talent_pool_memberships_processing_basis_check
  check (processing_basis is null or processing_basis in (
    'notice_and_consent',
    'legitimate_interests',
    'contractual_necessity',
    'legal_obligation',
    'public_task',
    'other_authorised_basis'
  ));
