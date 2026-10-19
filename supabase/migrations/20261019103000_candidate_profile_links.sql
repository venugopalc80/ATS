-- Persist reviewed professional links extracted from candidate CVs.
-- Apply to ATS-Staging only after review; production remains untouched.
alter table public.candidates
  add column if not exists profile_links jsonb not null default '[]'::jsonb;

alter table public.candidates
  drop constraint if exists candidates_profile_links_array_check;
alter table public.candidates
  add constraint candidates_profile_links_array_check
  check (jsonb_typeof(profile_links) = 'array' and jsonb_array_length(profile_links) <= 20);

alter table public.candidates
  drop constraint if exists candidates_profile_links_shape_check;
alter table public.candidates
  add constraint candidates_profile_links_shape_check
  check (
    not exists (
      select 1
      from jsonb_array_elements(profile_links) as item
      where jsonb_typeof(item) <> 'object'
         or jsonb_typeof(item->'type') <> 'string'
         or jsonb_typeof(item->'url') <> 'string'
         or item->>'type' not in ('linkedin', 'github', 'portfolio')
         or length(item->>'url') > 2048
         or (item->>'url') !~* '^https?://'
    )
  );
