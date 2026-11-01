"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiFetch, API_BASE } from "@/lib/api";
import { getActiveOrganizationId } from "@/lib/organization";

type Settings = { prefix: string; next_number: number; preview: string };

export default function OrganisationSettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [prefix, setPrefix] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    const organizationId = getActiveOrganizationId();
    if (!API_BASE || !organizationId) {
      setError("Select an organisation before managing its settings.");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const response = await apiFetch(
        API_BASE + "/api/me/organizations/" + encodeURIComponent(organizationId) + "/job-reference-settings",
        {},
        { preserveOrganization: true },
      );
      if (response.status === 403) throw new Error("Only organisation owners and admins can manage job reference settings.");
      if (!response.ok) throw new Error("Unable to load settings (HTTP " + response.status + ").");
      const data: Settings = await response.json();
      setSettings(data);
      setPrefix(data.prefix);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load organisation settings.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const organizationId = getActiveOrganizationId();
    if (!organizationId || !API_BASE) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const response = await apiFetch(
        API_BASE + "/api/me/organizations/" + encodeURIComponent(organizationId) + "/job-reference-settings",
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prefix }),
        },
        { preserveOrganization: true },
      );
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail || "Unable to save settings (HTTP " + response.status + ").");
      setSettings(body);
      setPrefix(body.prefix);
      setMessage("Job reference prefix saved. Existing job references have not changed.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to save settings.");
    } finally {
      setSaving(false);
    }
  }

  const preview = prefix.trim().toUpperCase() + "-" + String(settings?.next_number ?? 1).padStart(3, "0");

  return (
    <div className="shell">
      <aside className="sidebar">
        <Link href="/dashboard" className="brand">AQERITH</Link>
        <div className="nav-label">Administration</div>
        <Link href="/settings" className="nav-item active"><span aria-hidden="true">⚙</span><span>Organisation settings</span></Link>
        <Link href="/dashboard" className="nav-item"><span aria-hidden="true">⌂</span><span>Back to dashboard</span></Link>
      </aside>
      <main className="main">
        <header className="topbar"><span className="profile-link">Administration</span></header>
        <section className="content">
          <div className="header-row">
            <div>
              <div className="eyebrow">Organisation administration</div>
              <h1>Job reference settings</h1>
              <p className="subtitle">Choose the prefix used for automatically generated vacancy references.</p>
            </div>
          </div>
          {loading ? <p>Loading organisation settings…</p> : error ? <div className="notice error" role="alert">{error}</div> : (
            <section className="panel" style={{ maxWidth: 680, padding: 24 }}>
              <form onSubmit={save}>
                <label htmlFor="job-reference-prefix">Reference prefix</label>
                <input
                  id="job-reference-prefix"
                  name="prefix"
                  value={prefix}
                  onChange={(event) => setPrefix(event.target.value.toUpperCase())}
                  minLength={2}
                  maxLength={8}
                  pattern="[A-Za-z][A-Za-z0-9]{1,7}"
                  required
                  aria-describedby="prefix-help"
                />
                <p id="prefix-help" className="subtitle">Use 2–8 letters or numbers. Start with a letter. Example: AQE, NOR or ACME.</p>
                <div className="metric-card" style={{ margin: "20px 0", padding: 18 }}>
                  <div className="eyebrow">Next reference preview</div>
                  <strong style={{ fontSize: 24 }}>{preview}</strong>
                </div>
                <p className="subtitle">Changing the prefix affects new vacancies only. Existing job references remain unchanged, and the sequence will not be reset.</p>
                <div className="actions">
                  <button className="btn primary" type="submit" disabled={saving || !prefix.trim()}>{saving ? "Saving…" : "Save prefix"}</button>
                  <button className="btn" type="button" onClick={() => { setPrefix(settings?.prefix ?? ""); setMessage(""); setError(""); }}>Reset</button>
                </div>
              </form>
              {message && <p className="success-message" role="status">{message}</p>}
            </section>
          )}
        </section>
      </main>
    </div>
  );
}
