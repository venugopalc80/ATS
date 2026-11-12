-- AQERITH Recruitment Collaboration Hub (MVP)
-- Apply through the reviewed migration workflow; do not run against production directly.
create table if not exists public.conversations (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  kind text not null check (kind in ('direct','group')),
  title text,
  direct_key text,
  created_by uuid not null references public.profiles(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  archived_at timestamptz,
  constraint conversations_title_length check (title is null or length(trim(title)) between 1 and 120),
  constraint conversations_direct_key_kind check ((kind = 'direct' and direct_key is not null) or (kind = 'group' and direct_key is null))
);
create unique index if not exists conversations_direct_key_unique
  on public.conversations (organization_id, direct_key) where direct_key is not null;
create index if not exists conversations_org_updated_idx
  on public.conversations (organization_id, updated_at desc);

create table if not exists public.conversation_members (
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  user_id uuid not null references public.profiles(id) on delete cascade,
  member_role text not null default 'member' check (member_role in ('owner','member')),
  joined_at timestamptz not null default now(),
  left_at timestamptz,
  last_read_at timestamptz,
  is_pinned boolean not null default false,
  muted_until timestamptz,
  primary key (conversation_id, user_id)
);
create index if not exists conversation_members_user_idx
  on public.conversation_members (user_id, joined_at desc) where left_at is null;

create table if not exists public.messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  sender_user_id uuid not null references public.profiles(id),
  body text not null,
  created_at timestamptz not null default now(),
  edited_at timestamptz,
  deleted_at timestamptz,
  client_message_id uuid,
  constraint messages_body_length check (length(trim(body)) between 1 and 10000),
  unique (conversation_id, sender_user_id, client_message_id)
);
create index if not exists messages_conversation_cursor_idx
  on public.messages (conversation_id, created_at desc, id desc);

create table if not exists public.conversation_events (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  actor_user_id uuid not null references public.profiles(id),
  event_type text not null check (event_type in ('member_added','member_removed','member_left','title_changed')),
  target_user_id uuid references public.profiles(id),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists conversation_events_history_idx
  on public.conversation_events (conversation_id, created_at desc);

alter table public.conversations enable row level security;
alter table public.conversation_members enable row level security;
alter table public.messages enable row level security;
alter table public.conversation_events enable row level security;

-- The app accesses these tables through its authenticated FastAPI service layer.
-- Deny direct client access by default. Add narrowly scoped policies only if the
-- frontend is later approved to query these tables directly using Supabase.
revoke all on public.conversations, public.conversation_members, public.messages, public.conversation_events from anon, authenticated;
