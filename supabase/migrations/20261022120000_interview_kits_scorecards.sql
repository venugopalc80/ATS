-- AQERITH Idea 10: versioned interview kits and evidence-based scorecards.
-- Additive migration only. Apply to ATS-Staging after review; never apply to production as part of this PR.

-- Tenant-safe composite references. Idea 11 also creates these indexes; keep the
-- prerequisites here because this migration runs before the assessment migration.
create unique index if not exists jobs_organization_id_id_uidx on public.jobs(organization_id, id);
create unique index if not exists applications_organization_id_id_uidx on public.applications(organization_id, id);
create unique index if not exists interviews_organization_id_id_uidx on public.interviews(organization_id, id);
create unique index if not exists interviews_org_id_application_uidx on public.interviews(organization_id, id, application_id);

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
  foreign key (organization_id, job_id) references public.jobs(organization_id, id) on delete set null (job_id)
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
  foreign key (organization_id, interview_id, application_id) references public.interviews(organization_id, id, application_id) on delete cascade,
  foreign key (organization_id, application_id) references public.applications(organization_id, id) on delete cascade,
  foreign key (organization_id, template_id) references public.scorecard_templates(organization_id, id) on delete restrict,
  check ((status = 'draft' and submitted_at is null) or (status = 'submitted' and submitted_at is not null))
);

create table if not exists public.scorecard_responses (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  feedback_id uuid not null,
  competency_id uuid not null,
  rating smallint not null check (rating between 1 and 5),
  evidence text not null default '' check (length(trim(evidence)) between 0 and 4000),
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
  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end;
$$;

drop trigger if exists scorecard_template_immutable on public.scorecard_templates;
create trigger scorecard_template_immutable
before update on public.scorecard_templates
for each row execute function public.prevent_published_scorecard_template_mutation();

create or replace function public.prevent_published_scorecard_child_mutation()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
declare
  template_status text;
begin
  if tg_op <> 'INSERT' then
    select status into template_status
      from public.scorecard_templates
      where organization_id = old.organization_id and id = old.template_id;
    if template_status = 'published' then
      raise exception 'Published scorecard competencies and questions are immutable';
    end if;
  end if;
  if tg_op <> 'DELETE' then
    select status into template_status
      from public.scorecard_templates
      where organization_id = new.organization_id and id = new.template_id;
    if template_status = 'published' then
      raise exception 'Published scorecard competencies and questions are immutable';
    end if;
    return new;
  end if;
  return old;
end;
$$;

drop trigger if exists competency_template_immutable on public.competencies;
create trigger competency_template_immutable
before insert or update on public.competencies
for each row execute function public.prevent_published_scorecard_child_mutation();

drop trigger if exists interview_question_template_immutable on public.interview_kit_questions;
create trigger interview_question_template_immutable
before insert or update on public.interview_kit_questions
for each row execute function public.prevent_published_scorecard_child_mutation();

revoke all on function public.prevent_published_scorecard_template_mutation() from public;
revoke all on function public.prevent_published_scorecard_child_mutation() from public;


-- A submitted assessment is a durable record. Corrections require an explicit
-- future workflow rather than silently rewriting the assessor's original score.
create or replace function public.prevent_submitted_interview_feedback_mutation()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  if old.status = 'submitted' then
    raise exception 'Submitted interview feedback is immutable';
  end if;
  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end;
$$;

create or replace function public.prevent_submitted_scorecard_response_mutation()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
declare
  target_feedback_id uuid;
  target_organization_id uuid;
  feedback_status text;
begin
  if tg_op <> 'INSERT' then
    target_feedback_id := old.feedback_id;
    target_organization_id := old.organization_id;
    select status into feedback_status from public.interview_feedback
      where organization_id=target_organization_id and id=target_feedback_id;
    if feedback_status = 'submitted' then
      raise exception 'Responses to submitted interview feedback are immutable';
    end if;
  end if;
  if tg_op <> 'DELETE' then
    select status into feedback_status from public.interview_feedback
      where organization_id=new.organization_id and id=new.feedback_id;
    if feedback_status = 'submitted' then
      raise exception 'Responses to submitted interview feedback are immutable';
    end if;
    return new;
  end if;
  return old;
end;
$$;

drop trigger if exists interview_feedback_immutable on public.interview_feedback;
create trigger interview_feedback_immutable
before update on public.interview_feedback
for each row execute function public.prevent_submitted_interview_feedback_mutation();

drop trigger if exists scorecard_response_immutable on public.scorecard_responses;
create trigger scorecard_response_immutable
before insert or update on public.scorecard_responses
for each row execute function public.prevent_submitted_scorecard_response_mutation();

revoke all on function public.prevent_submitted_interview_feedback_mutation() from public;
revoke all on function public.prevent_submitted_scorecard_response_mutation() from public;


create table if not exists public.interview_scorecard_decisions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  interview_id uuid not null references public.interviews(id) on delete cascade,
  reviewer_id uuid not null references public.profiles(id) on delete restrict,
  decision text not null check (decision in ('proceed','decline','additional_interview','hold')),
  rationale text not null check (length(trim(rationale)) between 20 and 4000),
  evidence_snapshot jsonb not null check (jsonb_typeof(evidence_snapshot) = 'array' and jsonb_array_length(evidence_snapshot) > 0),
  created_at timestamptz not null default now(),
  unique (organization_id, id)
);
create index if not exists interview_scorecard_decisions_interview_idx
  on public.interview_scorecard_decisions(organization_id, interview_id, created_at desc);
alter table public.interview_scorecard_decisions enable row level security;
drop policy if exists interview_scorecard_decisions_member_all on public.interview_scorecard_decisions;
create policy interview_scorecard_decisions_member_all on public.interview_scorecard_decisions
  for all using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));
revoke all on public.interview_scorecard_decisions from anon, authenticated;

create or replace function public.prevent_interview_scorecard_decision_mutation()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  raise exception 'Recorded interview decisions are immutable; create a subsequent review record';
end;
$$;
drop trigger if exists interview_scorecard_decision_immutable on public.interview_scorecard_decisions;
create trigger interview_scorecard_decision_immutable
before update on public.interview_scorecard_decisions
for each row execute function public.prevent_interview_scorecard_decision_mutation();
revoke all on function public.prevent_interview_scorecard_decision_mutation() from public;
