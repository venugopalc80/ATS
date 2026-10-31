"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { apiFetch, API_BASE } from "@/lib/api";
import { getActiveOrganizationId } from "@/lib/organization";
import { getSupabaseClient } from "@/lib/supabase";

type Contact = { id: string; full_name: string; role: string };
type Message = { id: string; sender_user_id: string; body: string; created_at: string; deleted?: boolean };
type Conversation = {
  id: string; kind: "direct" | "group"; title: string | null; last_message: string | null;
  last_message_at: string | null; unread_count: number; is_pinned: boolean;
  members: Array<{ id: string; full_name: string | null; role: string }>;
};

const roleLabel = (role: string) => role.replaceAll("_", " ").replace(/\b\w/g, (s) => s.toUpperCase());
const timeLabel = (value: string | null) => value ? new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(new Date(value)) : "";

export default function CollaborationPage() {
  const organizationId = getActiveOrganizationId();
  const [tab, setTab] = useState<"pins" | "chats" | "contacts">("chats");
  const [search, setSearch] = useState("");
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState("");
  const [currentUserId, setCurrentUserId] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [hasMoreMessages, setHasMoreMessages] = useState(false);
  const [loadingOlderMessages, setLoadingOlderMessages] = useState(false);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [groupMode, setGroupMode] = useState(false);
  const [groupTitle, setGroupTitle] = useState("");
  const [selectedContactIds, setSelectedContactIds] = useState<string[]>([]);
  const [manageMembers, setManageMembers] = useState(false);
  const [addMemberIds, setAddMemberIds] = useState<string[]>([]);
  const [editedGroupTitle, setEditedGroupTitle] = useState("");

  const request = useCallback(async (path: string, init?: RequestInit) => {
    if (!API_BASE) throw new Error("AQERITH API is not configured.");
    const response = await apiFetch(API_BASE + path, init);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || "The collaboration request failed.");
    }
    return response.status === 204 ? null : response.json();
  }, []);

  const refresh = useCallback(async () => {
    if (!organizationId) { setLoading(false); setError("Choose an organisation before opening collaboration."); return; }
    try {
      setError("");
      const [chatData, contactData] = await Promise.all([
        request("/api/collaboration/conversations?organization_id=" + encodeURIComponent(organizationId)),
        request("/api/collaboration/contacts?organization_id=" + encodeURIComponent(organizationId)),
      ]);
      setConversations(chatData);
      setContacts(contactData);
      setActiveId((current) => current && chatData.some((c: Conversation) => c.id === current) ? current : (chatData[0]?.id ?? ""));
    } catch (e) { setError(e instanceof Error ? e.message : "Could not load collaboration."); }
    finally { setLoading(false); }
  }, [organizationId, request]);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { getSupabaseClient().auth.getUser().then(({ data }) => setCurrentUserId(data.user?.id ?? "")).catch(() => setCurrentUserId("")); }, []);

  const active = conversations.find((c) => c.id === activeId) ?? null;
  const loadMessages = useCallback(async (id: string, replace = false) => {
    try {
      const data: Message[] = await request("/api/collaboration/conversations/" + id + "/messages?limit=50");
      setMessages((current) => {
        if (replace) return data;
        const byId = new Map(current.map((message) => [message.id, message]));
        data.forEach((message) => byId.set(message.id, message));
        return Array.from(byId.values()).sort((a, b) =>
          a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id)
        );
      });
      if (replace) setHasMoreMessages(data.length === 50);
      await request("/api/collaboration/conversations/" + id + "/read", { method: "POST" });
      setConversations((items) => items.map((c) => c.id === id ? { ...c, unread_count: 0 } : c));
    } catch (e) { setError(e instanceof Error ? e.message : "Could not load messages."); }
  }, [request]);

  const loadOlderMessages = useCallback(async () => {
    if (!activeId || !messages.length || !hasMoreMessages || loadingOlderMessages) return;
    setLoadingOlderMessages(true);
    try {
      const cursor = messages[0].id;
      const data: Message[] = await request(
        "/api/collaboration/conversations/" + activeId + "/messages?limit=50&before_message_id=" + encodeURIComponent(cursor)
      );
      setMessages((current) => {
        const byId = new Map(data.map((message) => [message.id, message]));
        current.forEach((message) => byId.set(message.id, message));
        return Array.from(byId.values()).sort((a, b) =>
          a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id)
        );
      });
      setHasMoreMessages(data.length === 50);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not load older messages."); }
    finally { setLoadingOlderMessages(false); }
  }, [activeId, hasMoreMessages, loadingOlderMessages, messages, request]);

  useEffect(() => {
    setMessages([]);
    setHasMoreMessages(false);
    if (activeId) void loadMessages(activeId, true);
  }, [activeId, loadMessages]);

  // Poll the active thread until server-side realtime delivery is introduced.
  useEffect(() => {
    if (!activeId || !organizationId) return;
    const timer = window.setInterval(() => {
      void loadMessages(activeId);
      void request("/api/collaboration/conversations?organization_id=" + encodeURIComponent(organizationId))
        .then((data) => setConversations(data))
        .catch(() => undefined);
    }, 8000);
    return () => window.clearInterval(timer);
  }, [activeId, organizationId, loadMessages, request]);

  const filteredConversations = useMemo(() => {
    const base = tab === "pins" ? conversations.filter((c) => c.is_pinned) : conversations;
    const term = search.trim().toLowerCase();
    if (!term) return base;
    return base.filter((c) => (c.title || c.members.map((m) => m.full_name || "").join(" ")).toLowerCase().includes(term) || (c.last_message || "").toLowerCase().includes(term));
  }, [conversations, search, tab]);
  const filteredContacts = useMemo(() => contacts.filter((c) => (c.full_name + " " + c.role).toLowerCase().includes(search.toLowerCase())), [contacts, search]);

  async function startDirect(contact: Contact) {
    setBusy(true); setError("");
    try {
      const chat = await request("/api/collaboration/conversations", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ organization_id: organizationId, kind: "direct", member_ids: [contact.id] }),
      });
      await refresh(); setActiveId(chat.id); setTab("chats");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not start conversation."); }
    finally { setBusy(false); }
  }

  async function createGroup() {
    const title = groupTitle.trim();
    if (!title || selectedContactIds.length < 1 || busy) return;
    setBusy(true); setError("");
    try {
      const chat = await request("/api/collaboration/conversations", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ organization_id: organizationId, kind: "group", title, member_ids: selectedContactIds }),
      });
      setGroupMode(false); setGroupTitle(""); setSelectedContactIds([]);
      await refresh(); setActiveId(chat.id); setTab("chats");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not create group."); }
    finally { setBusy(false); }
  }

  async function addGroupMembers() {
    if (!activeId || addMemberIds.length === 0 || busy) return;
    setBusy(true); setError("");
    try {
      await request("/api/collaboration/conversations/" + activeId + "/members", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ member_ids: addMemberIds }),
      });
      setAddMemberIds([]); setManageMembers(false); await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not add group members."); }
    finally { setBusy(false); }
  }

  async function removeGroupMember(memberId: string) {
    if (!activeId || busy || !window.confirm("Remove this teammate from the group?")) return;
    setBusy(true); setError("");
    try {
      await request("/api/collaboration/conversations/" + activeId + "/members/" + memberId, { method: "DELETE" });
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not remove group member."); }
    finally { setBusy(false); }
  }

  async function saveGroupTitle() {
    const title = editedGroupTitle.trim();
    if (!activeId || !title || busy) return;
    setBusy(true); setError("");
    try {
      await request("/api/collaboration/conversations/" + activeId + "/title", {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      });
      setEditedGroupTitle(""); await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not update group title."); }
    finally { setBusy(false); }
  }

  async function leaveGroup() {
    if (!activeId || busy || !window.confirm("Leave this group conversation?")) return;
    setBusy(true); setError("");
    try {
      await request("/api/collaboration/conversations/" + activeId + "/leave", { method: "POST" });
      setActiveId(""); setMessages([]); await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not leave group."); }
    finally { setBusy(false); }
  }

  async function sendMessage(event: FormEvent) {
    event.preventDefault();
    if (!activeId || !draft.trim() || busy) return;
    setBusy(true); setError("");
    try {
      await request("/api/collaboration/conversations/" + activeId + "/messages", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body: draft.trim(), client_message_id: crypto.randomUUID() }),
      });
      setDraft(""); await loadMessages(activeId); await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Message could not be sent."); }
    finally { setBusy(false); }
  }

  async function togglePin(chat: Conversation) {
    try {
      await request("/api/collaboration/conversations/" + chat.id + "/pin?pinned=" + String(!chat.is_pinned), { method: "POST" });
      setConversations((items) => items.map((c) => c.id === chat.id ? { ...c, is_pinned: !c.is_pinned } : c));
    } catch (e) { setError(e instanceof Error ? e.message : "Could not update pin."); }
  }

  const activeTitle = active?.kind === "group" ? (active.title || "Group conversation") : active?.members.filter((m) => m.id !== currentUserId).map((m) => m.full_name).filter(Boolean).join(", ") || "Direct message";

  return (
    <main style={{ minHeight: "100vh", background: "#f5f6f8", color: "#1c2430", padding: "28px clamp(16px, 4vw, 48px)", fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, margin: "0 auto 22px", maxWidth: 1440 }}>
        <div><Link href="/dashboard" style={{ color: "#5c6878", fontSize: 13, textDecoration: "none" }}>← Back to workspace</Link><h1 style={{ fontSize: 28, margin: "8px 0 4px", letterSpacing: "-.7px" }}>Collaboration</h1><p style={{ margin: 0, color: "#657184", fontSize: 14 }}>Recruitment conversations, in context.</p></div>
        <div style={{ border: "1px solid #dce1e8", background: "#fff", borderRadius: 12, padding: "10px 13px", fontSize: 12, color: "#657184" }}>AQERITH · TEAM WORKSPACE</div>
      </header>
      {error && <div role="alert" style={{ maxWidth: 1440, margin: "0 auto 14px", padding: 12, borderRadius: 10, background: "#fff0ee", color: "#9d3024", border: "1px solid #ffd5ce" }}>{error}</div>}
      <section style={{ maxWidth: 1440, height: "min(740px, calc(100vh - 150px))", minHeight: 520, margin: "0 auto", display: "grid", gridTemplateColumns: "minmax(260px, 330px) minmax(0, 1fr)", background: "#fff", border: "1px solid #e0e4eb", borderRadius: 18, overflow: "hidden", boxShadow: "0 12px 36px #17233a0a" }}>
        <aside style={{ borderRight: "1px solid #e8ebf0", display: "flex", flexDirection: "column", minWidth: 0 }}>
          <div style={{ padding: 18, borderBottom: "1px solid #edf0f4" }}><strong style={{ fontSize: 16 }}>Team messages</strong><p style={{ margin: "5px 0 14px", fontSize: 12, color: "#778294" }}>Find a colleague or pick up a conversation.</p><input aria-label="Search conversations and contacts" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search people or messages…" style={{ width: "100%", boxSizing: "border-box", padding: "11px 12px", border: "1px solid #e0e5ec", borderRadius: 10, fontSize: 13, outlineColor: "#5468e8" }} /></div>
          <nav aria-label="Collaboration sections" style={{ display: "flex", gap: 4, padding: "12px 12px 4px" }}>
            {(["pins", "chats", "contacts"] as const).map((key) => <button key={key} onClick={() => setTab(key)} style={{ flex: 1, border: 0, borderRadius: 8, padding: "9px 4px", fontSize: 12, fontWeight: 650, textTransform: "capitalize", background: tab === key ? "#edf0ff" : "transparent", color: tab === key ? "#3549c7" : "#697587", cursor: "pointer" }}>{key === "pins" ? "My Pins" : key === "chats" ? "Chats" : "Contacts"}</button>)}
          </nav>
          <div style={{ overflowY: "auto", padding: 8, flex: 1 }}>
            {loading ? <p style={{ padding: 14, color: "#7a8595", fontSize: 13 }}>Loading your workspace…</p> :
              tab === "contacts" ? <>
                <div style={{ padding: "8px 8px 12px", display: "flex", gap: 8 }}>
                  <button onClick={() => { setGroupMode(false); setSelectedContactIds([]); }} style={{ flex: 1, border: "1px solid #e0e5ec", borderRadius: 8, padding: 8, background: !groupMode ? "#f0f2ff" : "#fff", color: "#46546a", cursor: "pointer", fontSize: 12 }}>Message</button>
                  <button onClick={() => setGroupMode(true)} style={{ flex: 1, border: "1px solid #e0e5ec", borderRadius: 8, padding: 8, background: groupMode ? "#f0f2ff" : "#fff", color: "#46546a", cursor: "pointer", fontSize: 12 }}>New group</button>
                </div>
                {groupMode && <div style={{ padding: 10, margin: "0 4px 10px", border: "1px solid #e0e5ec", borderRadius: 10 }}>
                  <label htmlFor="group-title" style={{ display: "block", fontSize: 12, fontWeight: 650, marginBottom: 6 }}>Group name</label>
                  <input id="group-title" value={groupTitle} onChange={(e) => setGroupTitle(e.target.value)} maxLength={120} placeholder="e.g. Product hiring team" style={{ width: "100%", boxSizing: "border-box", padding: 9, border: "1px solid #e0e5ec", borderRadius: 8, fontSize: 12 }} />
                  <button disabled={busy || !groupTitle.trim() || selectedContactIds.length === 0} onClick={() => void createGroup()} style={{ width: "100%", marginTop: 8, border: 0, borderRadius: 8, padding: 9, background: "#3549c7", color: "#fff", opacity: busy || !groupTitle.trim() || selectedContactIds.length === 0 ? .5 : 1, cursor: "pointer", fontSize: 12 }}>Create group ({selectedContactIds.length} selected)</button>
                </div>}
                {filteredContacts.map((c) => groupMode ?
                  <label key={c.id} style={{ display: "flex", gap: 10, alignItems: "center", padding: 12, borderRadius: 10, cursor: "pointer" }}>
                    <input type="checkbox" checked={selectedContactIds.includes(c.id)} onChange={(e) => setSelectedContactIds((ids) => e.target.checked ? [...ids, c.id] : ids.filter((id) => id !== c.id))} />
                    <span style={{ width: 34, height: 34, borderRadius: 11, display: "grid", placeItems: "center", background: "#e9edff", color: "#4054c5", fontWeight: 700 }}>{c.full_name.slice(0,1).toUpperCase()}</span>
                    <span><strong style={{ display: "block", fontSize: 13 }}>{c.full_name}</strong><small style={{ color: "#7b8595" }}>{roleLabel(c.role)}</small></span>
                  </label>
                : <button key={c.id} disabled={busy} onClick={() => void startDirect(c)} style={{ width: "100%", display: "flex", gap: 11, alignItems: "center", textAlign: "left", padding: 12, border: 0, borderRadius: 10, background: "white", cursor: "pointer" }}><span style={{ width: 36, height: 36, borderRadius: 12, display: "grid", placeItems: "center", background: "#e9edff", color: "#4054c5", fontWeight: 700 }}>{c.full_name.slice(0,1).toUpperCase()}</span><span style={{ minWidth: 0 }}><strong style={{ display: "block", fontSize: 13 }}>{c.full_name}</strong><small style={{ color: "#7b8595" }}>{roleLabel(c.role)} · Message</small></span></button>)}
              </> :
              filteredConversations.map((c) => {
                const otherNames = c.members.filter((m) => c.kind === "group" || m.id !== currentUserId).map((m) => m.full_name).filter(Boolean);
                const chatTitle = c.title || otherNames.join(", ") || "Direct message";
                return <button key={c.id} onClick={() => setActiveId(c.id)} style={{ width: "100%", display: "flex", gap: 10, alignItems: "flex-start", textAlign: "left", padding: 12, border: 0, borderRadius: 11, background: activeId === c.id ? "#f0f2ff" : "white", cursor: "pointer", marginBottom: 3 }}>
                  <span style={{ width: 38, height: 38, flexShrink: 0, borderRadius: 12, display: "grid", placeItems: "center", background: "#edf0f5", color: "#4e5b70", fontWeight: 700 }}>{chatTitle.slice(0,1).toUpperCase()}</span>
                  <span style={{ flex: 1, minWidth: 0 }}><span style={{ display: "flex", gap: 6, justifyContent: "space-between" }}><strong style={{ fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{chatTitle}</strong>{c.is_pinned && <span aria-label="Pinned" title="Pinned">⌖</span>}</span><span style={{ display: "block", color: "#7b8595", fontSize: 12, marginTop: 5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.last_message || "Start the conversation"}</span></span>
                  {c.unread_count > 0 && <span style={{ minWidth: 20, height: 20, borderRadius: 99, display: "grid", placeItems: "center", background: "#465be0", color: "white", fontSize: 11 }}>{c.unread_count}</span>}
                </button>;
              })}
            {!loading && tab !== "contacts" && filteredConversations.length === 0 && <div style={{ padding: 18, color: "#7a8595", fontSize: 13 }}>{tab === "pins" ? "Pin conversations to keep them close." : "No conversations yet. Open Contacts to message a teammate."}</div>}
            {!loading && tab === "contacts" && filteredContacts.length === 0 && <div style={{ padding: 18, color: "#7a8595", fontSize: 13 }}>No colleagues match that search.</div>}
          </div>
        </aside>
        <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
          {active ? <>
            <header style={{ padding: "17px 22px", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, borderBottom: "1px solid #edf0f4" }}><div><strong style={{ fontSize: 15 }}>{activeTitle}</strong><div style={{ fontSize: 12, color: "#7b8595", marginTop: 4 }}>{active.kind === "group" ? "Group conversation" : "Direct conversation"} · {active.members.length} member{active.members.length === 1 ? "" : "s"}</div></div><div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}>{active.kind === "group" && <><button onClick={() => setManageMembers((v) => !v)} style={{ border: "1px solid #e0e5ec", background: "#fff", borderRadius: 9, padding: "9px 10px", cursor: "pointer", color: "#46546a", fontSize: 12 }}>Members</button><button onClick={() => void leaveGroup()} disabled={busy} style={{ border: "1px solid #f0d6d3", background: "#fff", borderRadius: 9, padding: "9px 10px", cursor: "pointer", color: "#9d3024", fontSize: 12 }}>Leave</button></>}<button onClick={() => void togglePin(active)} style={{ border: "1px solid #e0e5ec", background: "#fff", borderRadius: 9, padding: "9px 12px", cursor: "pointer", color: "#46546a", fontSize: 12 }}>{active.is_pinned ? "Unpin" : "Pin conversation"}</button></div></header>
            {manageMembers && active.kind === "group" && <div style={{ padding: 14, borderBottom: "1px solid #edf0f4", background: "#fafbfc" }}>
              <strong style={{ fontSize: 12 }}>Group members</strong>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>{active.members.map((m) => <span key={m.id} style={{ border: "1px solid #e0e5ec", background: "#fff", borderRadius: 8, padding: "6px 8px", fontSize: 12, display: "inline-flex", gap: 6, alignItems: "center" }}>{m.full_name || "AQERITH user"}{m.id === currentUserId ? " (you)" : ""}{active.members.some((x) => x.id === currentUserId && x.role === "owner") && m.id !== currentUserId && <button disabled={busy} onClick={() => void removeGroupMember(m.id)} aria-label={"Remove " + (m.full_name || "member")} style={{ border: 0, background: "transparent", color: "#9d3024", cursor: "pointer", padding: 0 }}>×</button>}</span>)}</div>
              {active.members.some((m) => m.id === currentUserId && m.role === "owner") && <>
                <div style={{ marginTop: 12, fontSize: 12, fontWeight: 650 }}>Rename group</div>
                <div style={{ display: "flex", gap: 8, marginTop: 6 }}><input value={editedGroupTitle} onChange={(e) => setEditedGroupTitle(e.target.value)} placeholder={active.title || "Group name"} maxLength={120} style={{ flex: 1, minWidth: 0, border: "1px solid #e0e5ec", borderRadius: 8, padding: 8, fontSize: 12 }} /><button disabled={busy || !editedGroupTitle.trim()} onClick={() => void saveGroupTitle()} style={{ border: 0, borderRadius: 8, padding: "8px 10px", background: "#3549c7", color: "#fff", opacity: busy || !editedGroupTitle.trim() ? .5 : 1, cursor: "pointer", fontSize: 12 }}>Save</button></div>
                <div style={{ marginTop: 12, fontSize: 12, fontWeight: 650 }}>Add teammates</div>
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 7 }}>{contacts.filter((contact) => !active.members.some((m) => m.id === contact.id)).map((contact) => <label key={contact.id} style={{ fontSize: 12, display: "flex", gap: 5, alignItems: "center" }}><input type="checkbox" checked={addMemberIds.includes(contact.id)} onChange={(e) => setAddMemberIds((ids) => e.target.checked ? [...ids, contact.id] : ids.filter((id) => id !== contact.id))} />{contact.full_name}</label>)}</div>
                <button onClick={() => void addGroupMembers()} disabled={busy || addMemberIds.length === 0} style={{ marginTop: 10, border: 0, borderRadius: 8, padding: "8px 11px", background: "#3549c7", color: "#fff", opacity: busy || addMemberIds.length === 0 ? .5 : 1, cursor: "pointer", fontSize: 12 }}>Add selected members</button>
              </>}
            </div>}
            <div aria-live="polite" style={{ flex: 1, overflowY: "auto", padding: "20px clamp(14px, 3vw, 32px)", display: "flex", flexDirection: "column", gap: 14 }}>
              {hasMoreMessages && <button type="button" onClick={() => void loadOlderMessages()} disabled={loadingOlderMessages} style={{ alignSelf: "center", border: "1px solid #e0e5ec", borderRadius: 9, padding: "8px 12px", background: "#fff", color: "#536174", fontSize: 12, cursor: loadingOlderMessages ? "wait" : "pointer" }}>{loadingOlderMessages ? "Loading…" : "Load older messages"}</button>}
              {messages.length === 0 && <div style={{ margin: "auto", textAlign: "center", maxWidth: 300, color: "#7b8595" }}><div style={{ fontSize: 30, marginBottom: 8 }}>✳</div><strong style={{ color: "#344054" }}>Start a useful conversation</strong><p style={{ fontSize: 13, lineHeight: 1.6 }}>Coordinate a vacancy, share an update or agree on the next step.</p></div>}
              {messages.map((m) => <div key={m.id} style={{ alignSelf: m.sender_user_id === currentUserId ? "flex-end" : "flex-start", maxWidth: "80%" }}><div style={{ padding: "11px 14px", borderRadius: 14, background: "#f1f3f7", fontSize: 14, lineHeight: 1.55, overflowWrap: "anywhere" }}>{m.body}</div><div style={{ fontSize: 10, color: "#8a94a3", marginTop: 5 }}>{timeLabel(m.created_at)}</div></div>)}
            </div>
            <form onSubmit={sendMessage} style={{ padding: 16, borderTop: "1px solid #edf0f4" }}><div style={{ display: "flex", gap: 10, alignItems: "flex-end" }}><textarea aria-label="Write a message" value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void sendMessage(e as unknown as FormEvent); } }} placeholder="Write a message… (Enter to send)" rows={2} maxLength={10000} style={{ flex: 1, resize: "vertical", minWidth: 0, border: "1px solid #dfe4eb", borderRadius: 12, padding: 12, font: "inherit", fontSize: 13, outlineColor: "#5468e8" }} /><button type="submit" disabled={!draft.trim() || busy} style={{ border: 0, borderRadius: 11, padding: "12px 17px", background: "#3549c7", color: "#fff", fontWeight: 650, cursor: busy ? "wait" : "pointer", opacity: !draft.trim() || busy ? .55 : 1 }}>Send ↗</button></div><div style={{ fontSize: 11, color: "#929baa", marginTop: 8 }}>Internal AQERITH conversation · Updates every 8 seconds · Keep candidate details within authorised workflows.</div></form>
          </> : <div style={{ display: "grid", placeContent: "center", textAlign: "center", flex: 1, padding: 24 }}><div style={{ fontSize: 34, color: "#5265d7" }}>✳</div><h2 style={{ margin: "12px 0 6px", fontSize: 20 }}>Your team, in sync.</h2><p style={{ maxWidth: 320, color: "#7b8595", fontSize: 13, lineHeight: 1.6 }}>Select a conversation or choose Contacts to start messaging a colleague.</p><button onClick={() => setTab("contacts")} style={{ justifySelf: "center", marginTop: 10, padding: "10px 14px", border: 0, borderRadius: 9, background: "#3549c7", color: "white", cursor: "pointer" }}>Find a colleague</button></div>}
        </div>
      </section>
      <style jsx>{`@media (max-width: 760px) { main { padding: 16px !important; } section { grid-template-columns: minmax(0,1fr) !important; grid-template-rows: minmax(190px, 34%) minmax(0,1fr) !important; height: calc(100dvh - 130px) !important; min-height: 560px !important; } section > aside { border-right: 0 !important; border-bottom: 1px solid #e8ebf0 !important; min-height: 0 !important; } section > aside > div:first-child { padding: 10px !important; } section > aside > div:first-child p { display:none; } section > aside button { font-size: 11px !important; } section > aside nav { padding: 8px 4px 2px !important; } } @media (max-width: 420px) { main { padding: 10px !important; } section { height: calc(100dvh - 112px) !important; min-height: 540px !important; grid-template-rows: minmax(175px, 32%) minmax(0,1fr) !important; } } `}</style>
    </main>
  );
}
