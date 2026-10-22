"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
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
          scope: ["case_metadata"],
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
                      <button className="btn" disabled={Boolean(busyCase)} onClick={() => void requestAccess(item)}>{busyCase === item.id ? "Requesting…" : "Request 30-minute access"}</button>
                    </article>)}
                  </div>
                )}
              </section>
            </>
          ) : null}
        </section>
      </main>
    </div>
  );
}
