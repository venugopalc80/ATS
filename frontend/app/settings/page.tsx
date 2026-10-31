"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch, API_BASE } from "@/lib/api";
import { getActiveOrganizationId } from "@/lib/organization";

type Organization = { id: string; name: string; timezone: string; role: string };
const timezones = [
  ["Europe/London", "Europe/London (UK)"],
  ["America/New_York", "America/New_York (US Eastern)"],
  ["America/Chicago", "America/Chicago (US Central)"],
  ["America/Denver", "America/Denver (US Mountain)"],
  ["America/Los_Angeles", "America/Los_Angeles (US Pacific)"],
  ["Asia/Kolkata", "Asia/Kolkata (India)"],
  ["Australia/Sydney", "Australia/Sydney"],
  ["Australia/Perth", "Australia/Perth"],
  ["UTC", "UTC"],
];

export default function SettingsPage() {
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [timezone, setTimezone] = useState("UTC");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const organizationId = getActiveOrganizationId();
      if (!API_BASE || !organizationId) {
        setError("Select an organisation before changing its settings.");
        setLoading(false);
        return;
      }
      try {
        const response = await apiFetch(API_BASE + "/api/me");
        if (!response.ok) throw new Error("Unable to load organisation settings (HTTP " + response.status + ").");
        const data = await response.json();
        const active = (data.organizations as Organization[]).find((item) => item.id === organizationId);
        if (!active) throw new Error("The selected organisation is not available to your account.");
        if (!cancelled) {
          setOrganization(active);
          setTimezone(active.timezone || "UTC");
        }
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "Unable to load settings.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, []);

  async function save() {
    if (!organization) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const response = await apiFetch(API_BASE + "/api/me/organizations/" + organization.id + "/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ timezone }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail || "Unable to save organisation settings.");
      }
      const result = await response.json();
      setOrganization({ ...organization, timezone: result.organization.timezone });
      setMessage("Organisation timezone saved.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to save settings.");
    } finally {
      setSaving(false);
    }
  }

  const canEdit = organization?.role === "owner" || organization?.role === "admin";

  return (
    <div className="shell">
      <aside className="sidebar">
        <Link href="/dashboard" className="brand">AQERITH</Link>
        <div className="nav-label">Workspace</div>
        <Link href="/dashboard" className="nav-item"><span>⌂</span><span>Dashboard</span></Link>
        <Link href="/jobs" className="nav-item"><span>▣</span><span>Jobs</span></Link>
        <Link href="/candidates" className="nav-item"><span>♙</span><span>Candidates</span></Link>
        <Link href="/submissions" className="nav-item"><span>↗</span><span>Submissions</span></Link>
        <Link href="/interviews" className="nav-item"><span>◷</span><span>Interviews</span></Link>
        <Link href="/clients" className="nav-item"><span>□</span><span>Clients</span></Link>
        <Link href="/onboarding" className="nav-item"><span>✓</span><span>Onboarding</span></Link>
        <Link href="/offers" className="nav-item"><span>＄</span><span>Offers</span></Link>
        <Link href="/placements" className="nav-item"><span>◈</span><span>Placements</span></Link>
        <div className="nav-label">Administration</div>
        <Link href="/settings" className="nav-item active" aria-current="page"><span>⚙</span><span>Settings</span></Link>
      </aside>
      <main className="main">
        <header className="topbar"><span className="muted-small">{organization?.name || "Organisation settings"}</span></header>
        <section className="content">
          <div className="header-row">
            <div><div className="eyebrow">Administration</div><h1>Organisation settings</h1><p className="subtitle">Manage organisation-wide defaults used across recruitment workflows.</p></div>
            <Link href="/dashboard" className="btn">Back to dashboard</Link>
          </div>
          {loading ? <div className="card" role="status">Loading organisation settings…</div> : error ? <div className="dashboard-error" role="alert">{error}</div> : organization && (
            <section className="card" style={{ maxWidth: 720 }}>
              <div className="card-head"><span className="card-title">Regional settings</span><span className="badge blue">{organization.role}</span></div>
              <label style={{ display: "grid", gap: 8, maxWidth: 440, fontSize: 13, fontWeight: 650 }}>
                Organisation timezone
                <select className="filter" value={timezone} disabled={!canEdit || saving} onChange={(event) => setTimezone(event.target.value)}>
                  {timezones.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </label>
              <p className="muted-small" style={{ lineHeight: 1.6, marginTop: 12 }}>This timezone defines organisation-wide calendar boundaries, including the Dashboard's Interviews today metric and interview list filter. Daylight-saving changes are handled automatically.</p>
              {!canEdit && <p className="notice" role="status">Only organisation owners and administrators can change these settings. Contact an administrator if this timezone needs updating.</p>}
              {message && <p className="notice" role="status">{message}</p>}
              {error && <p className="dashboard-error" role="alert">{error}</p>}
              {canEdit && <div className="modal-actions" style={{ justifyContent: "flex-start" }}><button className="btn primary" disabled={saving || timezone === organization.timezone} onClick={save}>{saving ? "Saving…" : "Save settings"}</button></div>}
            </section>
          )}
        </section>
      </main>
    </div>
  );
}
