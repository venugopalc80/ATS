-- Section 9 / Idea 49: distinguish basic case metadata from customer-written case content.
-- Customer-written subject/description access requires an explicit case_content grant.
alter table public.support_access_grants
  drop constraint if exists support_access_grants_scope_check;

alter table public.support_access_grants
  add constraint support_access_grants_scope_check
  check (scope <@ array['case_metadata','case_content','case_messages']::text[]);

