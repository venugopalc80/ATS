-- Defence in depth: browser roles should not have direct write access to tag tables.
-- Tag writes are performed by the authenticated API after organisation/role checks.
revoke all privileges on table public.candidate_tags, public.candidate_tag_assignments from anon;
revoke insert, update, delete, truncate, references, trigger
  on table public.candidate_tags, public.candidate_tag_assignments
  from authenticated;
grant select on table public.candidate_tags, public.candidate_tag_assignments to authenticated;
