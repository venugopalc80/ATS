-- Global country support: ISO 3166-1 alpha-2 country codes.
-- Application validation accepts any two uppercase letters; country-specific
-- compliance rules will be layered on top of this global foundation.

alter table public.organizations
  drop constraint if exists organizations_country_code_check;

alter table public.jobs
  drop constraint if exists jobs_country_code_check;

alter table public.candidates
  drop constraint if exists candidates_country_code_check;
