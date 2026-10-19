-- Persist reviewed professional links extracted from candidate CVs.
-- Apply to ATS-Staging only after review; production remains untouched.
alter table public.candidates
  add column if not exists profile_links jsonb not null default '[]'::jsonb;

alter table public.candidates
  drop constraint if exists candidates_profile_links_array_check;
alter table public.candidates
  add constraint candidates_profile_links_array_check
  check (jsonb_typeof(profile_links) = 'array');
