"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiFetch, API_BASE } from "@/lib/api";
import { getActiveOrganizationId } from "@/lib/organization";

type RecruiterTask = {
  id: string;
  organization_id: string;
  title: string;
  description: string | null;
  task_type: "general" | "candidate_follow_up" | "vacancy_follow_up" | "interview_follow_up";
  status: "open" | "in_progress" | "completed" | "cancelled";
  priority: "low" | "normal" | "high" | "urgent";
  due_at: string | null;
  candidate_id: string | null;
  job_id: string | null;
  candidate_first_name?: string | null;
  candidate_last_name?: string | null;
  job_title?: string | null;
  assignee_name?: string | null;
};

const blank = { title: "", description: "", task_type: "general", priority: "normal", due_at: "" };

function localDateTimeToIso(value: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

export default function TasksPage() {
  const [organizationId, setOrganizationId] = useState("");
  const [tasks, setTasks] = useState<RecruiterTask[]>([]);
  const [form, setForm] = useState(blank);
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    setOrganizationId(getActiveOrganizationId(process.env.NEXT_PUBLIC_ORGANIZATION_ID ?? ""));
  }, []);

  useEffect(() => {
    if (typeof window !== "undefined" && new URLSearchParams(window.location.search).get("create") === "1") {
      setShowForm(true);
    }
  }, []);

  const loadTasks = useCallback(async () => {
    if (!API_BASE || !organizationId) {
      setLoading(false);
      setError("Choose an organisation to view recruiter tasks.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const response = await apiFetch(API_BASE + "/api/tasks?organization_id=" + encodeURIComponent(organizationId));
      if (!response.ok) throw new Error(response.status === 403 ? "You do not have access to these tasks." : "Tasks could not be loaded (HTTP " + response.status + ").");
      setTasks(await response.json());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Tasks could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [organizationId]);

  useEffect(() => { if (organizationId) void loadTasks(); }, [organizationId, loadTasks]);

  async function createTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!API_BASE || !organizationId || !form.title.trim()) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const response = await apiFetch(API_BASE + "/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          organization_id: organizationId,
          title: form.title.trim(),
          description: form.description.trim() || null,
          task_type: form.task_type,
          priority: form.priority,
          due_at: localDateTimeToIso(form.due_at),
        }),
      });
      if (!response.ok) throw new Error("Task could not be saved (HTTP " + response.status + ").");
      setForm(blank);
      setShowForm(false);
      setMessage("Task created.");
      await loadTasks();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Task could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  async function setStatus(task: RecruiterTask, status: "completed" | "in_progress") {
    if (!API_BASE) return;
    setError("");
    setMessage("");
    try {
      const response = await apiFetch(API_BASE + "/api/tasks/" + encodeURIComponent(task.id), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      if (!response.ok) throw new Error("Task status could not be updated (HTTP " + response.status + ").");
      setMessage(status === "completed" ? "Task marked complete." : "Task reopened.");
      await loadTasks();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Task status could not be updated.");
    }
  }

  const openTasks = tasks.filter((task) => task.status === "open" || task.status === "in_progress");
  const completedTasks = tasks.filter((task) => task.status === "completed");

  return (
    <main className="content dashboard-content">
      <div className="header-row">
        <div>
          <div className="eyebrow">Recruitment operations</div>
          <h1>Recruiter tasks</h1>
          <p className="subtitle">Track due work and candidate or vacancy follow-ups for your organisation.</p>
        </div>
        <div className="actions dashboard-actions">
          <Link href="/dashboard" className="btn">Back to dashboard</Link>
          <button type="button" className="btn primary" onClick={() => setShowForm((value) => !value)}>{showForm ? "Cancel" : "+ Add task"}</button>
        </div>
      </div>

      {error && <div className="dashboard-error" role="alert"><strong>Task action failed</strong><p>{error}</p><button className="btn" onClick={() => void loadTasks()}>Retry</button></div>}
      {message && <p role="status" className="dashboard-success">{message}</p>}

      {showForm && (
        <form className="card task-form" onSubmit={createTask}>
          <h2>Create a recruiter task</h2>
          <label>Task title<input required maxLength={200} value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} placeholder="e.g. Follow up with candidate after interview" /></label>
          <label>Details<textarea maxLength={5000} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} rows={3} /></label>
          <div className="task-form-grid">
            <label>Task type<select value={form.task_type} onChange={(event) => setForm({ ...form, task_type: event.target.value })}>
              <option value="general">General task</option><option value="candidate_follow_up">Candidate follow-up</option><option value="vacancy_follow_up">Vacancy follow-up</option><option value="interview_follow_up">Interview follow-up</option>
            </select></label>
            <label>Priority<select value={form.priority} onChange={(event) => setForm({ ...form, priority: event.target.value })}>
              <option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option>
            </select></label>
            <label>Due date and time<input type="datetime-local" value={form.due_at} onChange={(event) => setForm({ ...form, due_at: event.target.value })} /></label>
          </div>
          <button className="btn primary" type="submit" disabled={saving || !form.title.trim()}>{saving ? "Saving…" : "Create task"}</button>
        </form>
      )}

      <div className="metrics dashboard-metrics">
        <div className="card dashboard-metric-card"><div className="metric-title">Open tasks</div><div className="metric-value">{loading ? "—" : openTasks.length}</div></div>
        <div className="card dashboard-metric-card"><div className="metric-title">Completed tasks</div><div className="metric-value">{loading ? "—" : completedTasks.length}</div></div>
        <div className="card dashboard-metric-card"><div className="metric-title">Due or overdue</div><div className="metric-value">{loading ? "—" : openTasks.filter((task) => task.due_at && new Date(task.due_at) < new Date()).length}</div></div>
      </div>

      <section className="card task-list">
        <div className="card-head"><h2 className="card-title">Open and upcoming</h2><button type="button" className="btn" onClick={() => void loadTasks()} disabled={loading}>{loading ? "Refreshing…" : "Refresh"}</button></div>
        {loading ? <p>Loading tasks…</p> : openTasks.length === 0 ? <div className="dashboard-empty"><strong>No open tasks</strong><p>Create a task or follow-up to have it appear here and in dashboard priorities when due.</p></div> : (
          <div className="dashboard-priority-list">{openTasks.map((task) => (
            <article key={task.id} className="dashboard-priority-row task-row">
              <span className={"badge " + (task.priority === "urgent" || task.priority === "high" ? "amber" : "blue")}>{task.priority}</span>
              <div className="dashboard-priority-copy"><strong>{task.title}</strong><span>{task.description || task.task_type.replaceAll("_", " ")}</span><span>{task.due_at ? "Due " + new Date(task.due_at).toLocaleString() : "No due date"}{task.candidate_first_name ? " · " + task.candidate_first_name + " " + (task.candidate_last_name || "") : ""}{task.job_title ? " · " + task.job_title : ""}</span></div>
              <button type="button" className="btn" onClick={() => void setStatus(task, "completed")}>Mark complete</button>
            </article>
          ))}</div>
        )}
      </section>

      <section className="card task-list">
        <div className="card-head"><h2 className="card-title">Recently completed</h2></div>
        {loading ? <p>Loading tasks…</p> : completedTasks.length === 0 ? <div className="dashboard-empty"><p>Completed tasks will appear here.</p></div> : (
          <div className="dashboard-priority-list">{completedTasks.slice(0, 20).map((task) => (
            <article key={task.id} className="dashboard-priority-row task-row"><span className="badge green">Complete</span><div className="dashboard-priority-copy"><strong>{task.title}</strong><span>{task.description || task.task_type.replaceAll("_", " ")}</span></div><button type="button" className="btn" onClick={() => void setStatus(task, "in_progress")}>Reopen</button></article>
          ))}</div>
        )}
      </section>
    </main>
  );
}
