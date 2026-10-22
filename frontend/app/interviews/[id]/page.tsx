"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { apiFetch } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";
const transitions: Record<string, string[]> = {
  scheduled: ["completed", "cancelled", "rescheduled", "no_show"],
  rescheduled: ["scheduled", "cancelled", "no_show"],
  completed: [],
  cancelled: [],
  no_show: [],
};

function toLocalDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

export default function InterviewDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [interview, setInterview] = useState<any>();
  const [feedback, setFeedback] = useState("");
  const [outcome, setOutcome] = useState("");
  const [notes, setNotes] = useState("");
  const [status, setStatus] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [rescheduling, setRescheduling] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const response = await apiFetch(API_BASE + "/api/interviews/" + id);
        if (!response.ok) {
          setMessage(response.status === 404 ? "Interview not found." : "Unable to load interview.");
          return;
        }
        const value = await response.json();
        setInterview(value);
        setFeedback(value.feedback ?? "");
        setOutcome(value.outcome ?? "");
        setNotes(value.notes ?? "");
        setStatus(value.status);
        setScheduledAt(toLocalDateTime(value.scheduled_at));
      } catch {
        setMessage("Unable to load interview. Check your connection and try again.");
      }
    })();
  }, [id]);

  async function saveDetails() {
    setSaving(true);
    setMessage("");
    try {
      const response = await apiFetch(API_BASE + "/api/interviews/" + id, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ feedback, outcome, notes, status }),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        setMessage(data?.detail ?? "Unable to save interview details.");
        return;
      }
      setInterview(data);
      setStatus(data.status);
      setMessage("Interview details saved.");
    } catch {
      setMessage("Unable to save interview details. Check your connection and try again.");
    } finally {
      setSaving(false);
    }
  }

  async function reschedule() {
    if (!scheduledAt || !interview) {
      setMessage("Choose a new interview date and time.");
      return;
    }
    if (!["scheduled", "rescheduled"].includes(interview.status)) {
      setMessage("Only scheduled interviews can be rescheduled.");
      return;
    }
    const nextDate = new Date(scheduledAt);
    if (Number.isNaN(nextDate.getTime())) {
      setMessage("Enter a valid interview date and time.");
      return;
    }
    if (nextDate.getTime() === new Date(interview.scheduled_at).getTime()) {
      setMessage("Choose a different date or time before rescheduling.");
      return;
    }

    setRescheduling(true);
    setMessage("");
    try {
      const response = await apiFetch(API_BASE + "/api/interviews/" + id, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scheduled_at: nextDate.toISOString(),
          status: "rescheduled",
        }),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        setMessage(data?.detail ?? "Unable to reschedule interview.");
        return;
      }
      setInterview(data);
      setStatus(data.status);
      setScheduledAt(toLocalDateTime(data.scheduled_at));
      setMessage("Interview rescheduled.");
    } catch {
      setMessage("Unable to reschedule interview. Check your connection and try again.");
    } finally {
      setRescheduling(false);
    }
  }

  if (!interview) {
    return (
      <main className="p-8">
        <Link href="/interviews">← Interviews</Link>
        <h1 className="mt-6 text-2xl font-semibold">{message || "Loading interview…"}</h1>
      </main>
    );
  }

  const canReschedule = ["scheduled", "rescheduled"].includes(interview.status);

  return (
    <main className="p-8">
      <div className="flex flex-wrap items-center justify-between gap-3"><Link href="/interviews">← Interviews</Link><Link className="btn primary" href={"/interviews/" + id + "/scorecard"}>Open scorecard</Link></div>
      <h1 className="mt-5 text-3xl font-semibold">Interview details</h1>
      <p className="mt-2 text-gray-500">
        Current time: {new Date(interview.scheduled_at).toLocaleString()} · {interview.interview_type}
      </p>
      {message && <div className="notice mt-4" role="status">{message}</div>}

      <section className="card mt-8 max-w-3xl">
        <h2 className="card-title">Schedule</h2>
        {canReschedule ? (
          <>
            <label>
              New date and time (shown in your local timezone)
              <input
                type="datetime-local"
                value={scheduledAt}
                onChange={(event) => setScheduledAt(event.target.value)}
              />
            </label>
            <button className="btn" onClick={() => void reschedule()} disabled={rescheduling || saving}>
              {rescheduling ? "Rescheduling…" : "Reschedule interview"}
            </button>
          </>
        ) : (
          <p className="text-sm text-gray-500">
            This interview is {interview.status}; its schedule can no longer be changed here.
          </p>
        )}
      </section>

      <section className="card mt-6 max-w-3xl">
        <h2 className="card-title">Feedback and outcome</h2>
        <label>
          Status
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value={status}>{status}</option>
            {(transitions[status] ?? []).filter((value) => value !== status).map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          Feedback
          <textarea rows={8} value={feedback} onChange={(event) => setFeedback(event.target.value)} placeholder="Interviewer observations" />
        </label>
        <label>
          Outcome
          <input value={outcome} onChange={(event) => setOutcome(event.target.value)} placeholder="Strong hire, hold, reject…" />
        </label>
        <label>
          Notes
          <textarea rows={5} value={notes} onChange={(event) => setNotes(event.target.value)} />
        </label>
        <button className="btn primary" onClick={() => void saveDetails()} disabled={saving || rescheduling}>
          {saving ? "Saving…" : "Save feedback"}
        </button>
        <Link className="btn ml-2" href={`/submissions/${interview.application_id}`}>Open submission</Link>
      </section>
    </main>
  );
}
