"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiFetch, API_BASE } from "@/lib/api";
import { getActiveOrganizationId } from "@/lib/organization";

type SupportCase = {
  id: string;
  category: string;
  priority: string;
  status: string;
  subject: string;
  created_at: string;
  updated_at: string;
};

type AccessGrant = {
  id: string;
  support_case_id: string;
  purpose: string;
  scope: string[];
  requested_at: string;
  approved_at?: string | null;
  expires_at: string;
  revoked_at?: string | null;
};

export default function SupportPage() {
  const [organizationId, setOrganizationId] = useState("");
  const [cases, setCases] = useState<SupportCase[]>([]);
  const [grants, setGrants] = useState<AccessGrant[]>([]);
  const [category, setCategory] = useState("technical");
  const [subject, setSubject] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  const load = useCallback(async (orgId: string) => {
    try {
      const [casesResponse, grantsResponse] = await Promise.all([
        apiFetch(API_BASE + "/api/support/cases?organization_id=" + encodeURIComponent(orgId)),
        apiFetch(API_BASE + "/api/support/access-grants?organization_id=" + encodeURIComponent(orgId)),
      ]);
      const casesBody = await casesResponse.json().catch(() => ({}));
      const grantsBody = await grantsResponse.json().catch(() => ({}));
      if (!casesResponse.ok) throw new Error(casesBody.detail || "Unable to load support cases.");
      if (!grantsResponse.ok) throw new Error(grantsBody.detail || "Unable to load access requests. Owner/admin access may be required.");
      setCases(casesBody.cases ?? []);
      setGrants(grantsBody.grants ?? []);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load support information.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const orgId = getActiveOrganizationId();
    setOrganizationId(orgId);
    if (!orgId || !API_BASE) {
      setMessage(!orgId ? "Select or create a workspace first." : "The API is not configured.");
      setLoading(false);
      return;
    }
    void load(orgId);
  }, [load]);

  async function createCase(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    try {
      const response = await apiFetch(API_BASE + "/api/support/cases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ organization_id: organizationId, category, subject, description }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || "Unable to create support case.");
      setSubject("");
      setDescription("");
      setMessage("Support case created.");
      await load(organizationId);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to create support case.");
    } finally {
      setSaving(false);
    }
  }

  async function decideGrant(grant: AccessGrant, action: "approve" | "revoke") {
    setMessage("");
    try {
      const response = await apiFetch(API_BASE + "/api/support/access-grants/" + encodeURIComponent(grant.id) + "/" + action, { method: "POST" });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || "Unable to update support access.");
      setMessage(action === "approve" ? "Support access approved for the stated scope and expiry." : "Support access revoked.");
      await load(organizationId);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to update support access.");
    }
  }

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
        <Link href="/support" className="nav-item active" aria-current="page">Support</Link>
      </aside>
      <main className="main">
        <header className="topbar"><div><strong>Support</strong><div className="muted-small">Get help and review exceptional access requests</div></div><Link href="/help" className="btn">Help centre</Link></header>
        <section className="content">
          <div className="eyebrow">Customer support</div>
          <h1>How can we help?</h1>
          <p className="subtitle">Share enough detail to diagnose the issue, but do not include candidate documents, passwords or unnecessary personal data.</p>
          {message && <div className="notice" role="status">{message}</div>}
          <form className="card" onSubmit={createCase} style={{ maxWidth: 900, marginBottom: 24 }}>
            <h2 className="card-title">Open a support case</h2>
            <div className="grid" style={{ gridTemplateColumns: "minmax(180px, 1fr) 2fr", marginTop: 16 }}>
              <label>Category<select className="filter" style={{ display: "block", width: "100%", marginTop: 6 }} value={category} onChange={(e) => setCategory(e.target.value)}><option value="technical">Technical</option><option value="billing">Billing</option><option value="account">Account</option><option value="security">Security</option><option value="privacy">Privacy</option><option value="other">Other</option></select></label>
              <label>Subject<input className="filter" style={{ display: "block", width: "100%", marginTop: 6 }} required minLength={4} maxLength={180} value={subject} onChange={(e) => setSubject(e.target.value)} /></label>
            </div>
            <label style={{ display: "block", marginTop: 16 }}>What happened?<textarea className="filter" style={{ display: "block", width: "100%", minHeight: 120, marginTop: 6 }} required minLength={10} maxLength={8000} value={description} onChange={(e) => setDescription(e.target.value)} /></label>
            <button className="btn primary" style={{ marginTop: 16 }} disabled={saving}>{saving ? "Submitting…" : "Submit support case"}</button>
          </form>

          <section style={{ marginBottom: 28 }}>
            <div className="card-head"><h2>Support cases</h2><span className="muted-small">{cases.length} shown</span></div>
            {loading ? <div className="card">Loading support cases…</div> : cases.length === 0 ? <div className="card">No support cases yet.</div> : (
              <div style={{ display: "grid", gap: 10 }}>
                {cases.map((item) => <article className="card" key={item.id}>
                  <div className="card-head"><strong>{item.subject}</strong><span className={"badge " + (item.status === "resolved" || item.status === "closed" ? "green" : "blue")}>{item.status.replaceAll("_", " ")}</span></div>
                  <div className="muted-small">{item.category} · {item.priority} · Opened {new Date(item.created_at).toLocaleDateString()}</div>
                </article>)}
              </div>
            )}
          </section>

          <section>
            <div className="card-head"><h2>Support access requests</h2><span className="muted-small">Owner/admin approval required</span></div>
            {grants.length === 0 ? <div className="card">No support access requests.</div> : (
              <div style={{ display: "grid", gap: 10 }}>
                {grants.map((grant) => <article className="card" key={grant.id}>
                  <div className="card-head"><strong>{grant.purpose}</strong><span className={"badge " + (grant.revoked_at ? "amber" : grant.approved_at ? "green" : "blue")}>{grant.revoked_at ? "revoked" : grant.approved_at ? "approved" : "pending approval"}</span></div>
                  <p className="muted-small">Scope: {grant.scope.join(", ")} · Expires {new Date(grant.expires_at).toLocaleString()}</p>
                  {!grant.approved_at && !grant.revoked_at ? <button className="btn primary" onClick={() => void decideGrant(grant, "approve")}>Approve time-limited access</button> : null}
                  {grant.approved_at && !grant.revoked_at ? <button className="btn" onClick={() => void decideGrant(grant, "revoke")}>Revoke access now</button> : null}
                </article>)}
              </div>
            )}
          </section>
        </section>
      </main>
    </div>
  );
}
