"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch, API_BASE } from "@/lib/api";
import { getActiveOrganizationId } from "@/lib/organization";

const checklist = [
  { id: "workspace_created", title: "Create your workspace", description: "Set up the organisation that owns your recruitment records.", href: "/onboarding" },
  { id: "profile_reviewed", title: "Review your workspace settings", description: "Set the default country, currency, time zone and job preferences.", href: "/settings" },
  { id: "first_job_created", title: "Create your first job", description: "Add a vacancy and prepare its hiring workflow.", href: "/jobs" },
  { id: "first_candidate_added", title: "Add a candidate", description: "Create a candidate record with relevant, accurate information.", href: "/candidates" },
  { id: "first_application_created", title: "Connect a candidate to a job", description: "Create and manage an application through the recruitment process.", href: "/submissions" },
  { id: "team_access_reviewed", title: "Review team access", description: "Make sure team members have only the access they need.", href: "/settings" },
] as const;

type StepId = typeof checklist[number]["id"];

export default function GettingStartedPage() {
  const [organizationId, setOrganizationId] = useState("");
  const [completed, setCompleted] = useState<StepId[]>([]);
  const [dismissed, setDismissed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [savingStep, setSavingStep] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    const orgId = getActiveOrganizationId();
    setOrganizationId(orgId);
    if (!orgId || !API_BASE) {
      setMessage(!orgId ? "Select or create a workspace first." : "The onboarding API is not configured.");
      setLoading(false);
      return;
    }
    void (async () => {
      try {
        const response = await apiFetch(API_BASE + "/api/onboarding/progress?organization_id=" + encodeURIComponent(orgId));
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(body.detail || "Unable to load your checklist.");
        setCompleted((body.completed_steps ?? []) as StepId[]);
        setDismissed(Boolean(body.dismissed));
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Unable to load your checklist.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function persist(nextCompleted: StepId[], nextDismissed: boolean, key: string) {
    setSavingStep(key);
    setMessage("");
    try {
      const response = await apiFetch(API_BASE + "/api/onboarding/progress?organization_id=" + encodeURIComponent(organizationId), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ completed_steps: nextCompleted, dismissed: nextDismissed }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || "Unable to save onboarding progress.");
      setCompleted(body.completed_steps ?? nextCompleted);
      setDismissed(Boolean(body.dismissed));
      setMessage("Your progress is saved privately to your account.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to save progress.");
    } finally {
      setSavingStep("");
    }
  }

  function toggleStep(step: StepId) {
    const next = completed.includes(step) ? completed.filter((item) => item !== step) : [...completed, step];
    setCompleted(next);
    void persist(next, dismissed, step);
  }

  const percentage = Math.round((completed.length / checklist.length) * 100);

  return (
    <div className="shell">
      <aside className="sidebar">
        <Link href="/" className="brand">AQERITH<span>.</span></Link>
        <div className="nav-label">Workspace</div>
        <Link href="/" className="nav-item">Overview</Link>
        <Link href="/jobs" className="nav-item">Jobs</Link>
        <Link href="/candidates" className="nav-item">Candidates</Link>
        <Link href="/clients" className="nav-item">Clients</Link>
        <div className="nav-label">Account</div>
        <Link href="/settings" className="nav-item">Organisation settings</Link>
        <Link href="/billing" className="nav-item">Plans & billing</Link>
        <Link href="/help" className="nav-item">Help centre</Link>
        <Link href="/onboarding/checklist" className="nav-item active" aria-current="page">Getting started</Link>
      </aside>
      <main className="main">
        <header className="topbar"><div><strong>Getting started</strong><div className="muted-small">A personal checklist for your workspace</div></div><Link href="/help" className="btn">Open help centre</Link></header>
        <section className="content">
          <div className="eyebrow">Onboarding</div>
          <h1>Build your recruitment workspace</h1>
          <p className="subtitle">Your checklist progress is private to your user account, even when you belong to a shared organisation.</p>
          {message && <div className="notice" role="status">{message}</div>}
          {loading ? <div className="card">Loading your checklist…</div> : (
            <>
              <div className="card" style={{ marginBottom: 18 }}>
                <div className="card-head"><strong>{completed.length} of {checklist.length} steps complete</strong><span className="badge blue">{percentage}%</span></div>
                <div style={{ height: 8, background: "#e7eaf0", borderRadius: 999, overflow: "hidden" }}><div style={{ height: "100%", width: percentage + "%", background: "#3157d5", transition: "width .2s ease" }} /></div>
              </div>
              <div style={{ display: "grid", gap: 12 }}>
                {checklist.map((step) => (
                  <article className="card" key={step.id} style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
                    <input aria-label={"Mark " + step.title + " complete"} type="checkbox" checked={completed.includes(step.id)} disabled={Boolean(savingStep)} onChange={() => toggleStep(step.id)} style={{ marginTop: 5, width: 18, height: 18 }} />
                    <div style={{ flex: 1 }}>
                      <strong>{step.title}</strong>
                      <p className="muted-small" style={{ margin: "6px 0 10px" }}>{step.description}</p>
                      <Link className="link" href={step.href}>Open this area ↗</Link>
                    </div>
                    {completed.includes(step.id) && <span className="badge green">Complete</span>}
                  </article>
                ))}
              </div>
              <div className="actions" style={{ marginTop: 20 }}>
                <button className="btn" disabled={Boolean(savingStep)} onClick={() => void persist(completed, !dismissed, "dismiss")}>{dismissed ? "Resume checklist" : "Dismiss checklist"}</button>
                <Link className="btn" href="/help">Browse help articles</Link>
              </div>
            </>
          )}
        </section>
      </main>
    </div>
  );
}
