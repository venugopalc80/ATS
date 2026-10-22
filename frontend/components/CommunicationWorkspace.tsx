"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";

type Thread = { id: string; subject?: string | null; created_at: string };
type TimelineMessage = {
  id: string;
  visibility: "candidate" | "internal";
  channel: string;
  body_text: string;
  subject?: string | null;
  status: string;
  created_at: string;
  recipients: { id: string; recipient_address: string; delivery_status: string }[];
  delivery_events: { id: string; provider: string; event_type: string; occurred_at: string }[];
};

export default function CommunicationWorkspace({
  applicationId,
  organizationId,
  candidateEmail,
}: {
  applicationId: string;
  organizationId: string;
  candidateEmail?: string | null;
}) {
  const [thread, setThread] = useState<Thread | null>(null);
  const [messages, setMessages] = useState<TimelineMessage[]>([]);
  const [note, setNote] = useState("");
  const [draft, setDraft] = useState("");
  const [subject, setSubject] = useState("Recruitment update");
  const [recipient, setRecipient] = useState(candidateEmail ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const q = new URLSearchParams({ organization_id: organizationId, application_id: applicationId });
      const response = await apiFetch(`${API_BASE}/api/communications/threads?${q}`);
      if (!response.ok) throw new Error("Unable to load communications.");
      const threads = (await response.json()) as Thread[];
      const selected = threads[0] ?? null;
      setThread(selected);
      if (selected) {
        const timelineQuery = new URLSearchParams({ organization_id: organizationId });
        const timelineResponse = await apiFetch(
          `${API_BASE}/api/communications/threads/${selected.id}/timeline?${timelineQuery}`,
        );
        if (!timelineResponse.ok) throw new Error("Unable to load the communication timeline.");
        setMessages((await timelineResponse.json()) as TimelineMessage[]);
      } else {
        setMessages([]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to load communications.");
    }
  }, [applicationId, organizationId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function ensureThread() {
    if (thread) return thread;
    const response = await apiFetch(`${API_BASE}/api/communications/threads`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        organization_id: organizationId,
        application_id: applicationId,
        subject: "Application communication",
      }),
    });
    if (!response.ok) throw new Error("Unable to create a communication thread.");
    const created = (await response.json()) as Thread;
    setThread(created);
    return created;
  }

  async function submitNote(event: FormEvent) {
    event.preventDefault();
    if (!note.trim()) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const current = await ensureThread();
      const q = new URLSearchParams({ organization_id: organizationId });
      const response = await apiFetch(
        `${API_BASE}/api/communications/threads/${current.id}/notes?${q}`,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ body_text: note }) },
      );
      if (!response.ok) throw new Error("Unable to save the internal note.");
      setNote("");
      setNotice("Internal note saved. It is not candidate-visible.");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to save the note.");
    } finally {
      setBusy(false);
    }
  }

  async function submitDraft(event: FormEvent) {
    event.preventDefault();
    if (!draft.trim() || !recipient.trim()) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const current = await ensureThread();
      const q = new URLSearchParams({ organization_id: organizationId });
      const response = await apiFetch(
        `${API_BASE}/api/communications/threads/${current.id}/messages?${q}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            body_text: draft,
            subject,
            channel: "email",
            recipient_address: recipient,
            idempotency_key: `ui-${crypto.randomUUID()}`,
          }),
        },
      );
      if (!response.ok) throw new Error("Unable to save the message draft.");
      setDraft("");
      setNotice("Draft saved. Sending is not enabled until an email provider is configured.");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to save the draft.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card mt-4" aria-label="Application communications">
      <div className="card-head">
        <span className="card-title">Communication timeline</span>
        <span className="muted-small">{messages.length} events</span>
      </div>
      {error && <p role="alert" className="notice">{error}</p>}
      {notice && <p role="status" className="notice">{notice}</p>}
      <div className="space-y-3">
        {messages.map((message) => (
          <article key={message.id} className="border-b pb-3">
            <div className="flex flex-wrap items-center gap-2">
              <strong>{message.visibility === "internal" ? "Internal note" : "Candidate message draft"}</strong>
              <span className="muted-small">{message.status}</span>
              <span className="muted-small">{new Date(message.created_at).toLocaleString()}</span>
            </div>
            {message.subject && <p className="mt-1 font-medium">{message.subject}</p>}
            <p className="mt-1 whitespace-pre-wrap">{message.body_text}</p>
            {message.recipients.map((r) => (
              <p key={r.id} className="muted-small">To {r.recipient_address} · {r.delivery_status}</p>
            ))}
            {message.delivery_events.map((event) => (
              <p key={event.id} className="muted-small">
                {event.event_type} · {event.provider} · {new Date(event.occurred_at).toLocaleString()}
              </p>
            ))}
          </article>
        ))}
        {!messages.length && <p className="text-gray-500">No communication events recorded for this application.</p>}
      </div>
      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <form onSubmit={submitNote} className="space-y-2">
          <h3 className="font-medium">Internal note</h3>
          <p className="muted-small">Visible only to authorised AQERITH users. Never sent to the candidate.</p>
          <textarea className="input min-h-24 w-full" value={note} onChange={(e) => setNote(e.target.value)} maxLength={20000} required aria-label="Internal note" />
          <button className="btn" type="submit" disabled={busy || !note.trim()}>Save internal note</button>
        </form>
        <form onSubmit={submitDraft} className="space-y-2">
          <h3 className="font-medium">Candidate email draft</h3>
          <p className="muted-small">Draft only. Delivery is disabled until a provider and verified delivery webhook are configured.</p>
          <label className="block text-sm">Recipient
            <input className="input mt-1 w-full" type="email" value={recipient} onChange={(e) => setRecipient(e.target.value)} required maxLength={320} />
          </label>
          <label className="block text-sm">Subject
            <input className="input mt-1 w-full" value={subject} onChange={(e) => setSubject(e.target.value)} required maxLength={500} />
          </label>
          <label className="block text-sm">Message
            <textarea className="input mt-1 min-h-24 w-full" value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={20000} required />
          </label>
          <button className="btn" type="submit" disabled={busy || !draft.trim() || !recipient.trim()}>Save email draft</button>
        </form>
      </div>
    </section>
  );
}
