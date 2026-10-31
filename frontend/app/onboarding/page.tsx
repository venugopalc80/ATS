"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, API_BASE } from "@/lib/api";
import { supabase } from "@/lib/supabase";

export default function OnboardingPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [country, setCountry] = useState("GB");
  const [timezone, setTimezone] = useState("Europe/London");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage("");

    try {
      const response = await apiFetch(API_BASE + "/api/me/organizations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, country_code: country, timezone }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail || "Unable to create organization.");
      }

      const result = await response.json();
      window.localStorage.setItem("aqerith_active_org", result.organization.id);
      window.localStorage.setItem("talentos_active_org", result.organization.id);
      router.replace("/");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to create workspace.");
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    await supabase.auth.signOut();
    router.replace("/login");
  }

  return (
    <main className="auth-page">
      <section className="auth-card">
        <div className="brand">Talent<span>OS</span></div>
        <div className="eyebrow">Workspace setup</div>
        <h1>Create your recruitment workspace</h1>
        <p className="subtitle">Your account is ready. Set up the organisation that will own your jobs, candidates and applications.</p>
        <form onSubmit={submit} className="auth-form">
          <label>Organisation name<input required minLength={2} value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme Recruitment" /></label>
          <label>Primary country code<input required maxLength={2} pattern="[A-Za-z]{2}" value={country} onChange={(e) => setCountry(e.target.value.toUpperCase())} placeholder="GB" /><small className="muted-small">Use the ISO 3166-1 alpha-2 code for your primary country, e.g. GB, US, DE, AE.</small></label>
          <label>Organisation timezone<select required value={timezone} onChange={(e) => setTimezone(e.target.value)}><option value="Europe/London">Europe/London (UK)</option><option value="America/New_York">America/New_York (US Eastern)</option><option value="America/Chicago">America/Chicago (US Central)</option><option value="America/Denver">America/Denver (US Mountain)</option><option value="America/Los_Angeles">America/Los_Angeles (US Pacific)</option><option value="Asia/Kolkata">Asia/Kolkata (India)</option><option value="Australia/Sydney">Australia/Sydney</option><option value="Australia/Perth">Australia/Perth</option><option value="UTC">UTC</option></select><small className="muted-small">Used for organisation-wide dates such as interviews scheduled today.</small></label>
          <button className="btn primary auth-submit" disabled={busy}>{busy ? "Creating..." : "Create workspace"}</button>
        </form>
        {message && <div className="notice">{message}</div>}
        <button className="auth-switch" onClick={signOut}>Sign out</button>
      </section>
    </main>
  );
}
