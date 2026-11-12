"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { apiFetch } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";
const TRANSITIONS: Record<string, string[]> = {
  scheduled: ["completed", "cancelled", "rescheduled", "no_show"],
  rescheduled: ["scheduled", "completed", "cancelled", "no_show"],
  completed: [],
  cancelled: [],
  no_show: [],
};

type Interview = {
  id: string;
  application_id: string;
  scheduled_at: string;
  interview_type: string;
  status: string;
  notes?: string | null;
  feedback?: string | null;
  outcome?: string | null;
  feedback_author_id?: string | null;
  feedback_at?: string | null;
};

export default function InterviewDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [interview, setInterview] = useState<Interview | null>(null);
  const [feedback, setFeedback] = useState("");
  const [outcome, setOutcome] = useState("");
  const [notes, setNotes] = useState("");
  const [status, setStatus] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const response = await apiFetch(API_BASE + "/api/interviews/" + id);
        const body = await response.json().catch(() => null);
        if (!response.ok) throw new Error(body?.detail || "Interview not found.");
        if (!active) return;
        setInterview(body);
        setFeedback(body.feedback || "");
        setOutcome(body.outcome || "");
        setNotes(body.notes || "");
        setStatus(body.status);
      } catch (error) {
        if (active) setMessage(error instanceof Error ? error.message : "Unable to load interview.");
      }
    })();
    return () => { active = false; };
  }, [id]);

  async function save() {
    setMessage("");
    try {
      const response = await apiFetch(API_BASE + "/api/interviews/" + id, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ feedback, outcome, notes, status }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail || "Unable to save interview.");
      setInterview(body);
      setFeedback(body.feedback || "");
      setOutcome(body.outcome || "");
      setNotes(body.notes || "");
      setStatus(body.status);
      setMessage("Interview updated.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to save interview.");
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

  return (
    <main className="p-8">
      <Link href="/interviews">← Interviews</Link>
      <h1 className="mt-5 text-3xl font-semibold">Interview feedback</h1>
      <p className="mt-2 text-gray-500">
        {new Date(interview.scheduled_at).toLocaleString()} · {interview.interview_type}
      </p>
      {message && <div className="notice mt-4" role="status">{message}</div>}
      <section className="card mt-8 max-w-3xl">
        <label>
          Status
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value={status}>{status}</option>
            {(TRANSITIONS[status] || []).map((nextStatus) => (
              <option key={nextStatus} value={nextStatus}>{nextStatus}</option>
            ))}
          </select>
        </label>
        <label>
          Feedback
          <textarea
            rows={8}
            value={feedback}
            onChange={(event) => setFeedback(event.target.value)}
            placeholder="Interviewer observations"
          />
        </label>
        {interview.feedback_at && (
          <p className="muted-small">
            Feedback last changed {new Date(interview.feedback_at).toLocaleString()}
            {interview.feedback_author_id ? " · Author attribution recorded" : ""}
          </p>
        )}
        <label>
          Outcome
          <input
            value={outcome}
            onChange={(event) => setOutcome(event.target.value)}
            placeholder="Strong hire, hold, reject…"
          />
        </label>
        <label>
          Notes
          <textarea rows={5} value={notes} onChange={(event) => setNotes(event.target.value)} />
        </label>
        <button className="btn primary" onClick={() => void save()}>Save feedback</button>
        <Link className="btn ml-2" href={`/submissions/${interview.application_id}`}>Open submission</Link>
      </section>
    </main>
  );
}
