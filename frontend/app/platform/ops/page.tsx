"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiFetch, API_BASE } from "@/lib/api";

type SupportCase = {
  id: string;
  organization_id: string;
  category: string;
  priority: string;
  status: string;
  subject: string;
  created_at: string;
};

type CaseDetail = SupportCase & { description: string; resolved_at?: string | null };
type SupportMessage = { id: string; author_user_id?: string | null; author_operator_id?: string | null; visibility: "customer" | "internal"; body: string; created_at: string };

type Health = {
  status: string;
  database: string;
  checked_at: string;
  support_cases_by_status: { status: string; count: number }[];
};

export default function PlatformOperationsPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [cases, setCases] = useState<SupportCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [busyCase, setBusyCase] = useState("");
  const [selectedCase, setSelectedCase] = useState<CaseDetail | null>(null);
  const [caseMessages, setCaseMessages] = useState<SupportMessage[]>([]);
  const [reply, setReply] = useState("");
  const [visibility, setVisibility] = useState<"customer" | "internal">("customer");

  const load = useCallback(async () => {
    if (!API_BASE) {
      setMessage("The API is not configured.");
      setLoading(false);
      return;
    }
    try {
      const [healthResponse, casesResponse] = await Promise.all([
        apiFetch(API_BASE + "/api/platform/health"),
        apiFetch(API_BASE + "/api/platform/support/cases?limit=50"),
      ]);
      const healthBody = await healthResponse.json().catch(() => ({}));
      const casesBody = await casesResponse.json().catch(() => ({}));
      if (!healthResponse.ok || !casesResponse.ok) {
        const body = !healthResponse.ok ? healthBody : casesBody;
        throw new Error(body.detail || "Platform operator access is required.");
      }
      setHealth(healthBody);
      setCases(casesBody.cases ?? []);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load platform operations.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function requestAccess(item: SupportCase) {
    setBusyCase(item.id);
    setMessage("");
    try {
      const response = await apiFetch(API_BASE + "/api/platform/support/access-grants", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          organization_id: item.organization_id,
          support_case_id: item.id,
          purpose: "Investigate support case: " + item.subject,
          scope: ["case_metadata", "case_messages"],
          duration_minutes: 30,
        }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || "Unable to request support access.");
      setMessage("A case-specific access request was sent to the organisation's owners/admins for approval.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to request support access.");
    } finally {
      setBusyCase("");
    }
  }

  async function openCase(item: SupportCase) {
    setBusyCase(item.id);
    setMessage("");
    setSelectedCase(null);
    setCaseMessages([]);
    try {
      const [caseResponse, messagesResponse] = await Promise.all([
        apiFetch(API_BASE + "/api/platform/support/cases/" + encodeURIComponent(item.id)),
        apiFetch(API_BASE + "/api/platform/support/cases/" + encodeURIComponent(item.id) + "/messages"),
      ]);
      const caseBody = await caseResponse.json().catch(() => ({}));
      if (!caseResponse.ok) throw new Error(caseBody.detail || "Approved case access is required.");
      const messagesBody = await messagesResponse.json().catch(() => ({}));
      if (!messagesResponse.ok) throw new Error(messagesBody.detail || "Approved message access is required.");
      setSelectedCase(caseBody);
      setCaseMessages(messagesBody.messages ?? []);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to open support case. Check the customer's approved access grant.");
    } finally {
      setBusyCase("");
    }
  }

  async function sendOperatorReply(event: FormEvent) {
    event.preventDefault();
    if (!selectedCase || !reply.trim()) return;
    setBusyCase(selectedCase.id);
    setMessage("");
    try {
      const response = await apiFetch(API_BASE + "/api/platform/support/cases/" + encodeURIComponent(selectedCase.id) + "/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body: reply.trim(), visibility }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || "Unable to send support reply.");
      setCaseMessages((current) => [...current, body]);
      setReply("");
      setMessage(visibility === "customer" ? "Customer-visible reply sent." : "Internal note saved.");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to send support reply.");
    } finally {
      setBusyCase("");
    }
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <Link href="/" className="brand">AQERITH<span>.</span></Link>
        <div className="nav-label">Platform</div>
        <Link href="/platform/ops" className="nav-item active" aria-current="page">Operations health</Link>
        <Link href="/support" className="nav-item">Customer support</Link>
        <div className="nav-label">Workspace</div>
        <Link href="/" className="nav-item">Return to AQERITH</Link>
      </aside>
      <main className="main">
        <header className="topbar"><div><strong>Platform operations</strong><div className="muted-small">Restricted internal view</div></div><button className="btn" onClick={() => void load()}>Refresh</button></header>
        <section className="content">
          <div className="eyebrow">Platform administration</div>
          <h1>Service health & support queue</h1>
          <p className="subtitle">This page requires a separately provisioned platform-operator role. Customer organisation roles do not grant platform access.</p>
          {message && <div className="notice" role="status">{message}</div>}
          {loading ? <div className="card">Loading platform health…</div> : health ? (
            <>
              <div className="metrics">
                <div className="card"><div className="metric-title">API data access</div><div className="metric-value">{health.status}</div><div className="metric-foot">Health endpoint responded</div></div>
                <div className="card"><div className="metric-title">Database</div><div className="metric-value">{health.database}</div><div className="metric-foot">Connection check passed</div></div>
                <div className="card"><div className="metric-title">Open support cases</div><div className="metric-value">{health.support_cases_by_status.filter((item) => !["resolved", "closed"].includes(item.status)).reduce((sum, item) => sum + Number(item.count), 0)}</div><div className="metric-foot">Across all organisations</div></div>
                <div className="card"><div className="metric-title">Last checked</div><div className="metric-value" style={{ fontSize: 17 }}>{new Date(health.checked_at).toLocaleTimeString()}</div><div className="metric-foot">{new Date(health.checked_at).toLocaleDateString()}</div></div>
              </div>
              <section>
                <div className="card-head"><h2>Support queue</h2><span className="muted-small">{cases.length} cases shown</span></div>
                {cases.length === 0 ? <div className="card">No support cases are waiting.</div> : (
                  <div style={{ display: "grid", gap: 10 }}>
                    {cases.map((item) => <article className="card" key={item.id}>
                      <div className="card-head"><strong>{item.subject}</strong><span className={"badge " + (item.priority === "urgent" || item.priority === "high" ? "amber" : "blue")}>{item.priority}</span></div>
                      <p className="muted-small">{item.category} · {item.status.replaceAll("_", " ")} · Organisation {item.organization_id}</p>
                      <p className="muted-small">Case content is hidden until an organisation admin approves a case-specific, time-limited support grant.</p>
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                        <button className="btn" disabled={Boolean(busyCase)} onClick={() => void requestAccess(item)}>{busyCase === item.id ? "Working…" : "Request 30-minute access"}</button>
                        <button className="btn primary" disabled={Boolean(busyCase)} onClick={() => void openCase(item)}>{busyCase === item.id ? "Opening…" : "Open approved case"}</button>
                      </div>
                    </article>)}
                  </div>
                )}
                {selectedCase && <article className="card" style={{ marginTop: 18, border: "1px solid var(--border, #d7dce2)" }}>
                  <div className="card-head"><h2>{selectedCase.subject}</h2><button className="btn" onClick={() => { setSelectedCase(null); setCaseMessages([]); }}>Close case view</button></div>
                  <p className="muted-small">{selectedCase.category} · {selectedCase.priority} · {selectedCase.status.replaceAll("_", " ")}</p>
                  <div style={{ whiteSpace: "pre-wrap", margin: "12px 0 18px" }}>{selectedCase.description}</div>
                  <h3>Conversation and notes</h3>
                  <div style={{ display: "grid", gap: 8, margin: "12px 0" }}>
                    {caseMessages.map((entry) => <div className="notice" key={entry.id}>
                      <div className="muted-small">{entry.visibility === "internal" ? "Internal note" : "Customer-visible"} · {new Date(entry.created_at).toLocaleString()}</div>
                      <div style={{ whiteSpace: "pre-wrap" }}>{entry.body}</div>
                    </div>)}
                    {caseMessages.length === 0 && <p className="muted-small">No messages yet.</p>}
                  </div>
                  <form onSubmit={(event) => void sendOperatorReply(event)}>
                    <label>Reply type<select className="filter" style={{ display: "block", width: "100%", maxWidth: 320, marginTop: 6 }} value={visibility} onChange={(event) => setVisibility(event.target.value as "customer" | "internal")}>
                      <option value="customer">Reply to customer</option><option value="internal">Internal note</option>
                    </select></label>
                    <label style={{ display: "block", marginTop: 12 }}>Message<textarea className="filter" style={{ display: "block", width: "100%", minHeight: 90, marginTop: 6 }} required maxLength={8000} value={reply} onChange={(event) => setReply(event.target.value)} /></label>
                    <button className="btn primary" style={{ marginTop: 10 }} type="submit" disabled={Boolean(busyCase) || !reply.trim()}>{busyCase === selectedCase.id ? "Sending…" : "Send message"}</button>
                  </form>
                </article>}
              </section>
            </>
          ) : null}
        </section>
      </main>
    </div>
  );
}
