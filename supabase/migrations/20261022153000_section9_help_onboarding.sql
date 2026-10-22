-- Per-user onboarding progress and versioned, searchable help content.
create table if not exists public.onboarding_progress (
  organization_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid not null references public.profiles(id) on delete cascade,
  completed_steps jsonb not null default '[]'::jsonb check (jsonb_typeof(completed_steps) = 'array'),
  dismissed boolean not null default false,
  updated_at timestamptz not null default now(),
  primary key (organization_id, user_id)
);
alter table public.onboarding_progress enable row level security;
create policy onboarding_progress_owner_read
  on public.onboarding_progress for select to authenticated
  using (user_id = auth.uid() and public.is_org_member(organization_id));
revoke insert, update, delete on public.onboarding_progress from anon, authenticated;
grant select on public.onboarding_progress to authenticated;

create table if not exists public.help_articles (
  id uuid primary key default gen_random_uuid(),
  slug text not null,
  locale text not null default 'en-GB',
  version integer not null default 1 check (version > 0),
  title text not null check (length(trim(title)) between 3 and 180),
  category text not null check (length(trim(category)) between 2 and 60),
  summary text not null check (length(trim(summary)) between 5 and 300),
  body_markdown text not null,
  published boolean not null default false,
  updated_at timestamptz not null default now(),
  unique (slug, locale, version)
);
create index if not exists help_articles_search_idx
  on public.help_articles(locale, category, published, updated_at desc);
alter table public.help_articles enable row level security;
create policy help_articles_published_read
  on public.help_articles for select to authenticated
  using (published = true);
revoke insert, update, delete on public.help_articles from anon, authenticated;
grant select on public.help_articles to authenticated;

insert into public.help_articles
  (slug, locale, version, title, category, summary, body_markdown, published)
values
  ('create-first-job', 'en-GB', 1, 'Create your first job', 'Jobs',
   'Set up a vacancy and keep its hiring workflow in one workspace.',
   $article$## Create a job
1. Open **Jobs** from the workspace navigation.
2. Choose the action to create a job and enter its title, location, employment type and description.
3. Save the job as a draft while details are being reviewed, or open it when it is ready to recruit.

Keep the job description focused on role requirements and avoid unnecessary personal or protected-characteristic criteria.$article$,
   true),
  ('manage-candidates', 'en-GB', 1, 'Manage candidates responsibly', 'Candidates',
   'Keep candidate records accurate and limit access to people who need it.',
   $article$## Candidate records
1. Open **Candidates** to find or add a candidate.
2. Keep contact details and work-related information accurate and relevant.
3. Use the application workflow to connect a candidate to a vacancy.
4. Follow your organisation’s privacy notice, retention policy and applicable data-protection obligations.

Do not add sensitive personal information unless there is a clear lawful and operational need.$article$,
   true),
  ('organisation-settings', 'en-GB', 1, 'Configure organisation settings', 'Settings',
   'Set workspace defaults for country, currency, time zone and job creation.',
   $article$## Workspace defaults
1. Open **Organisation settings**.
2. Update the brand name, country code, currency, time zone, date format and default job options.
3. Save your changes. Each successful save creates a new version and an audit record.

Only organisation owners and admins can change settings. Historical recruitment events should not be rewritten when defaults change.$article$,
   true),
  ('roles-and-access', 'en-GB', 1, 'Understand workspace access', 'Security',
   'Use organisation roles to grant only the access each team member needs.',
   $article$## Access basics
- **Owner/Admin:** manage organisation-level settings and access-sensitive operations.
- **Recruiter/Hiring manager/Viewer:** use the capabilities allowed by their assigned role.

Invite only people who need access, review memberships regularly and do not share login credentials. Role availability and individual permissions may depend on the current product configuration.$article$,
   true)
on conflict (slug, locale, version) do nothing;
