-- AQERITH Idea 10: versioned interview kits and evidence-based scorecards.
-- Additive migration only. Apply to ATS-Staging after review; never apply to production as part of this PR.

create table if not exists public.interview_kits (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  job_id uuid,
  name text not null check (length(trim(name)) between 1 and 160),
  description text,
  status text not null default 'draft' check (status in ('draft','published','archived')),
  current_version_id uuid,
  created_by uuid references public.profiles(id) on delete set null,
  updated_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, id),
  foreign key (job_id) references public.jobs(id) on delete set null
);

create table if not exists public.scorecard_templates (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  kit_id uuid not null,
  version_number integer not null check (version_number > 0),
  instructions text,
  status text not null default 'draft' check (status in ('draft','published')),
  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  published_at timestamptz,
  unique (organization_id, id),
  unique (kit_id, version_number),
  foreign key (organization_id, kit_id) references public.interview_kits(organization_id, id) on delete cascade
);

alter table public.interview_kits
  drop constraint if exists interview_kits_current_version_fk;
alter table public.interview_kits
  add constraint interview_kits_current_version_fk
  foreign key (organization_id, current_version_id)
  references public.scorecard_templates(organization_id, id) on delete set null (current_version_id);

create table if not exists public.competencies (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  template_id uuid not null,
  competency_key text not null check (length(trim(competency_key)) between 1 and 80),
  name text not null check (length(trim(name)) between 1 and 160),
  description text not null check (length(trim(description)) between 1 and 2000),
  rating_guidance jsonb not null default '{}'::jsonb check (jsonb_typeof(rating_guidance) = 'object'),
  display_order integer not null default 0,
  unique (organization_id, id),
  unique (template_id, competency_key),
  foreign key (organization_id, template_id) references public.scorecard_templates(organization_id, id) on delete cascade
);

create table if not exists public.interview_kit_questions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  template_id uuid not null,
  competency_id uuid not null,
  question text not null check (length(trim(question)) between 1 and 2000),
  evaluation_guidance text,
  display_order integer not null default 0,
  foreign key (organization_id, template_id) references public.scorecard_templates(organization_id, id) on delete cascade,
  foreign key (organization_id, competency_id) references public.competencies(organization_id, id) on delete cascade
);

create table if not exists public.interview_feedback (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  interview_id uuid not null,
  application_id uuid not null,
  interviewer_id uuid not null references public.profiles(id) on delete restrict,
  template_id uuid not null,
  status text not null default 'draft' check (status in ('draft','submitted')),
  overall_summary text,
  strengths text,
  concerns text,
  submitted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, id),
  unique (organization_id, interview_id, interviewer_id),
  foreign key (interview_id) references public.interviews(id) on delete cascade,
  foreign key (application_id) references public.applications(id) on delete cascade,
  foreign key (organization_id, template_id) references public.scorecard_templates(organization_id, id) on delete restrict,
  check ((status = 'draft' and submitted_at is null) or (status = 'submitted' and submitted_at is not null))
);

create table if not exists public.scorecard_responses (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  feedback_id uuid not null,
  competency_id uuid not null,
  rating smallint not null check (rating between 1 and 5),
  evidence text not null check (length(trim(evidence)) between 1 and 4000),
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (feedback_id, competency_id),
  foreign key (organization_id, feedback_id) references public.interview_feedback(organization_id, id) on delete cascade,
  foreign key (organization_id, competency_id) references public.competencies(organization_id, id) on delete restrict
);

create index if not exists interview_kits_org_status_idx
  on public.interview_kits(organization_id, status, updated_at desc);
create index if not exists scorecard_templates_kit_version_idx
  on public.scorecard_templates(organization_id, kit_id, version_number desc);
create index if not exists interview_feedback_interview_idx
  on public.interview_feedback(organization_id, interview_id, status);
create index if not exists scorecard_responses_feedback_idx
  on public.scorecard_responses(organization_id, feedback_id);

alter table public.interview_kits enable row level security;
alter table public.scorecard_templates enable row level security;
alter table public.competencies enable row level security;
alter table public.interview_kit_questions enable row level security;
alter table public.interview_feedback enable row level security;
alter table public.scorecard_responses enable row level security;

drop policy if exists interview_kits_member_all on public.interview_kits;
create policy interview_kits_member_all on public.interview_kits
  for all using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));
drop policy if exists scorecard_templates_member_all on public.scorecard_templates;
create policy scorecard_templates_member_all on public.scorecard_templates
  for all using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));
drop policy if exists competencies_member_all on public.competencies;
create policy competencies_member_all on public.competencies
  for all using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));
drop policy if exists interview_kit_questions_member_all on public.interview_kit_questions;
create policy interview_kit_questions_member_all on public.interview_kit_questions
  for all using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));
drop policy if exists interview_feedback_member_all on public.interview_feedback;
create policy interview_feedback_member_all on public.interview_feedback
  for all using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));
drop policy if exists scorecard_responses_member_all on public.scorecard_responses;
create policy scorecard_responses_member_all on public.scorecard_responses
  for all using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));

-- Browser clients cannot bypass API-level interviewer/manager permissions.
revoke all on public.interview_kits, public.scorecard_templates, public.competencies,
  public.interview_kit_questions, public.interview_feedback, public.scorecard_responses
  from anon, authenticated;


-- Published versions are immutable. New changes must create a new version.
create or replace function public.prevent_published_scorecard_template_mutation()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if old.status = 'published' then
    raise exception 'Published scorecard templates are immutable; create a new version';
  end if;
  return case when tg_op = 'DELETE' then old else new end;
end;
$$;

drop trigger if exists scorecard_template_immutable on public.scorecard_templates;
create trigger scorecard_template_immutable
before update or delete on public.scorecard_templates
for each row execute function public.prevent_published_scorecard_template_mutation();

create or replace function public.prevent_published_scorecard_child_mutation()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
declare
  target_template_id uuid;
  target_organization_id uuid;
  template_status text;
begin
  if tg_op = 'DELETE' then
    target_template_id := old.template_id;
    target_organization_id := old.organization_id;
  else
    target_template_id := new.template_id;
    target_organization_id := new.organization_id;
  end if;
  select status into template_status
    from public.scorecard_templates
    where organization_id = target_organization_id and id = target_template_id;
  if template_status = 'published' then
    raise exception 'Published scorecard competencies and questions are immutable';
  end if;
  return case when tg_op = 'DELETE' then old else new end;
end;
$$;

drop trigger if exists competency_template_immutable on public.competencies;
create trigger competency_template_immutable
before insert or update or delete on public.competencies
for each row execute function public.prevent_published_scorecard_child_mutation();

drop trigger if exists interview_question_template_immutable on public.interview_kit_questions;
create trigger interview_question_template_immutable
before insert or update or delete on public.interview_kit_questions
for each row execute function public.prevent_published_scorecard_child_mutation();

revoke all on function public.prevent_published_scorecard_template_mutation() from public;
revoke all on function public.prevent_published_scorecard_child_mutation() from public;
