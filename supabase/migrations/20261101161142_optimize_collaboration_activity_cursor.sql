-- Keep the group activity keyset-pagination query aligned with its sort order.
-- The leading conversation_id scopes reads; created_at + id provide a stable cursor.
drop index if exists public.conversation_events_history_idx;

create index if not exists conversation_events_history_cursor_idx
  on public.conversation_events (conversation_id, created_at desc, id desc);
