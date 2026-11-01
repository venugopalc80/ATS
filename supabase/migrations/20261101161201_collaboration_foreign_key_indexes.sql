-- Add covering indexes for collaboration foreign keys identified by Supabase's
-- performance advisor. These support profile/user deletes and creator lookups.
create index if not exists conversation_events_actor_user_idx
  on public.conversation_events (actor_user_id);

create index if not exists conversation_events_target_user_idx
  on public.conversation_events (target_user_id)
  where target_user_id is not null;

create index if not exists conversations_created_by_idx
  on public.conversations (created_by);

create index if not exists messages_sender_user_idx
  on public.messages (sender_user_id);
