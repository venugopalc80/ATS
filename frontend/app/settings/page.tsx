"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { apiFetch, API_BASE } from "@/lib/api";
import { getActiveOrganizationId } from "@/lib/organization";

type Settings = {
  brand_name: string;
  default_country_code: string;
  default_currency: string;
  timezone: string;
  date_format: "DD/MM/YYYY" | "MM/DD/YYYY" | "YYYY-MM-DD";
  job_default_work_mode: "onsite" | "hybrid" | "remote";
  job_default_employment_type: "permanent" | "contract" | "temporary" | "internship";
};

const defaults: Settings = {
  brand_name: "AQERITH",
  default_country_code: "GB",
  default_currency: "GBP",
  timezone: "UTC",
  date_format: "DD/MM/YYYY",
  job_default_work_mode: "hybrid",
  job_default_employment_type: "permanent",
};

export default function OrganizationSettingsPage() {
  const [organizationId, setOrganizationId] = useState("");
  const [settings, setSettings] = useState<Settings>(defaults);
  const [version, setVersion] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    const orgId = getActiveOrganizationId();
    setOrganizationId(orgId);
    if (!orgId || !API_BASE) {
      setMessage(!orgId ? "Select or create a workspace first." : "The API is not configured.");
      setLoading(false);
      return;
    }
    void (async () => {
      try {
        const response = await apiFetch(API_BASE + "/api/organizations/" + encodeURIComponent(orgId) + "/settings");
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(body.detail || "Unable to load organisation settings.");
        setSettings({ ...defaults, ...(body.settings ?? {}) });
        setVersion(body.version ?? 0);
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Unable to load settings.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  function update<K extends keyof Settings>(key: K, value: Settings[K]) {
    setSettings((current) => ({ ...current, [key]: value }));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    try {
      const response = await apiFetch(API_BASE + "/api/organizations/" + encodeURIComponent(organizationId) + "/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || "Unable to save settings. Owner or admin access may be required.");
      setSettings({ ...defaults, ...(body.settings ?? {}) });
      setVersion(body.version ?? version);
      setMessage("Settings saved as version " + (body.version ?? version) + ".");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to save settings.");
    } finally {
      setSaving(false);
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
        <Link href="/settings" className="nav-item active" aria-current="page">Organisation settings</Link>
        <Link href="/billing" className="nav-item">Plans & billing</Link>
      </aside>
      <main className="main">
        <header className="topbar">
          <div><strong>Organisation settings</strong><div className="muted-small">Workspace defaults and customisation</div></div>
          <Link href="/" className="btn">Back to workspace</Link>
        </header>
        <section className="content">
          <div className="eyebrow">Workspace configuration</div>
          <h1>Organisation settings</h1>
          <p className="subtitle">Changes create a new settings version and are recorded in the organisation audit trail. Only owners and admins can save changes.</p>
          {message && <div className="notice" role="status">{message}</div>}
          {loading ? <div className="card">Loading settings…</div> : (
            <form className="card" onSubmit={save} style={{ maxWidth: 860 }}>
              <div className="card-head">
                <div><div className="card-title">Workspace defaults</div><div className="muted-small">Current settings version: {version}</div></div>
              </div>
              <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}>
                <label>Brand name<input className="filter" required minLength={2} maxLength={100} value={settings.brand_name} onChange={(e) => update("brand_name", e.target.value)} /></label>
                <label>Default country code<input className="filter" required maxLength={2} pattern="[A-Z]{2}" value={settings.default_country_code} onChange={(e) => update("default_country_code", e.target.value.toUpperCase())} /></label>
                <label>Default currency<input className="filter" required maxLength={3} pattern="[A-Z]{3}" value={settings.default_currency} onChange={(e) => update("default_currency", e.target.value.toUpperCase())} /></label>
                <label>Time zone<input className="filter" required value={settings.timezone} onChange={(e) => update("timezone", e.target.value)} placeholder="Europe/London" /><small className="muted-small">Use an IANA time zone, e.g. Europe/London.</small></label>
                <label>Date format<select className="filter" value={settings.date_format} onChange={(e) => update("date_format", e.target.value as Settings["date_format"])}><option>DD/MM/YYYY</option><option>MM/DD/YYYY</option><option>YYYY-MM-DD</option></select></label>
                <label>Default work mode<select className="filter" value={settings.job_default_work_mode} onChange={(e) => update("job_default_work_mode", e.target.value as Settings["job_default_work_mode"])}><option value="onsite">On-site</option><option value="hybrid">Hybrid</option><option value="remote">Remote</option></select></label>
                <label>Default employment type<select className="filter" value={settings.job_default_employment_type} onChange={(e) => update("job_default_employment_type", e.target.value as Settings["job_default_employment_type"])}><option value="permanent">Permanent</option><option value="contract">Contract</option><option value="temporary">Temporary</option><option value="internship">Internship</option></select></label>
              </div>
              <div className="actions" style={{ marginTop: 24 }}><button className="btn primary" disabled={saving}>{saving ? "Saving…" : "Save settings"}</button><button className="btn" type="button" disabled={saving} onClick={() => setSettings(defaults)}>Reset form</button></div>
            </form>
          )}
        </section>
      </main>
    </div>
  );
}
