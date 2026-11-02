"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { apiFetch, API_BASE } from "@/lib/api";
import { getActiveOrganizationId } from "@/lib/organization";

type Organization = { id: string; name: string; timezone: string; role: string };
type Invitation = { id: string; email: string; role: string; expires_at: string; created_at: string };
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
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("recruiter");
  const [inviting, setInviting] = useState(false);
  const [inviteMessage, setInviteMessage] = useState("");
  const [inviteError, setInviteError] = useState("");
  const [inviteLink, setInviteLink] = useState("");

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
          if (active.role === "owner" || active.role === "admin") {
            const inviteResponse = await apiFetch(API_BASE + "/api/me/organizations/" + active.id + "/invitations");
            if (inviteResponse.ok) {
              const inviteData = await inviteResponse.json();
              setInvitations(inviteData.invitations || []);
            }
          }
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

  async function sendInvitation(event: FormEvent) {
    event.preventDefault();
    if (!organization) return;
    setInviting(true);
    setInviteMessage("");
    setInviteError("");
    try {
      const response = await apiFetch(API_BASE + "/api/me/organizations/" + organization.id + "/invitations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: inviteEmail, role: inviteRole }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail || "Unable to send invitation.");
      setInviteEmail("");
      setInviteLink(body.email_sent ? "" : (body.invite_url || ""));
      setInviteMessage(body.email_sent ? "Invitation email sent to " + body.invitation.email + ". The link expires in 7 days." : "The invitation is ready, but email delivery was unavailable. Copy the secure link below and share it with the invited person. They must sign in with the invited email address.");
      const refreshed = await apiFetch(API_BASE + "/api/me/organizations/" + organization.id + "/invitations");
      if (refreshed.ok) { const data = await refreshed.json(); setInvitations(data.invitations || []); }
    } catch (cause) {
      setInviteError(cause instanceof Error ? cause.message : "Unable to send invitation.");
    } finally {
      setInviting(false);
    }
  }

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
                <input id="organization-timezone" name="organization-timezone" className="filter" list="aqerith-timezones" value={timezone} disabled={!canEdit || saving} onChange={(event) => setTimezone(event.target.value)} placeholder="Europe/London" />
                <datalist id="aqerith-timezones"><option value="Europe/London" /><option value="America/New_York" /><option value="America/Chicago" /><option value="America/Denver" /><option value="America/Los_Angeles" /><option value="Asia/Kolkata" /><option value="Asia/Singapore" /><option value="Australia/Sydney" /><option value="Australia/Perth" /><option value="Pacific/Auckland" /><option value="UTC" /></datalist>
              </label>
              <p className="muted-small" style={{ lineHeight: 1.6, marginTop: 12 }}>Enter any valid IANA timezone. This timezone defines organisation-wide calendar boundaries and interview display times. Daylight-saving changes are handled automatically.</p>
              {!canEdit && <p className="notice" role="status">Only organisation owners and administrators can change these settings. Contact an administrator if this timezone needs updating.</p>}
              {message && <p className="notice" role="status">{message}</p>}
              {error && <p className="dashboard-error" role="alert">{error}</p>}
              {canEdit && <div className="modal-actions" style={{ justifyContent: "flex-start" }}><button className="btn primary" disabled={saving || timezone === organization.timezone} onClick={save}>{saving ? "Saving…" : "Save settings"}</button></div>}
            </section>
          )}
          {canEdit && organization && (
            <section className="card" style={{ maxWidth: 900, marginTop: 20 }}>
              <div className="card-head"><span className="card-title">Team members</span><span className="badge blue">Owner / Admin</span></div>
              <p className="muted-small" style={{ lineHeight: 1.6 }}>Invite colleagues into this organisation. They will share its recruitment workspace, with permissions determined by the role you assign.</p>
              <form onSubmit={sendInvitation} style={{ display: "grid", gridTemplateColumns: "minmax(220px, 1fr) 180px auto", gap: 12, alignItems: "end", marginTop: 16 }}>
                <label style={{ display: "grid", gap: 7, fontSize: 13, fontWeight: 650 }}>Work email
                  <input className="filter" type="email" required value={inviteEmail} onChange={(event) => setInviteEmail(event.target.value)} placeholder="colleague@agency.com" />
                </label>
                <label style={{ display: "grid", gap: 7, fontSize: 13, fontWeight: 650 }}>Workspace role
                  <select className="filter" value={inviteRole} onChange={(event) => setInviteRole(event.target.value)}>
                    <option value="recruiter">Recruiter</option>
                    <option value="hiring_manager">Hiring manager</option>
                    <option value="viewer">Viewer</option>
                    <option value="admin">Administrator</option>
                  </select>
                </label>
                <button className="btn primary" disabled={inviting}>{inviting ? "Sending…" : "Send invitation"}</button>
              </form>
              {inviteMessage && <p className="notice" role="status">{inviteMessage}</p>}
              {inviteError && <p className="dashboard-error" role="alert">{inviteError}</p>}
              {inviteLink && <div style={{ display: "grid", gap: 8, marginTop: 12 }}><input className="filter" readOnly value={inviteLink} aria-label="Secure invitation link" /><button type="button" className="btn" onClick={() => navigator.clipboard.writeText(inviteLink)}>Copy invitation link</button></div>}
              <div style={{ marginTop: 22 }}>
                <div className="card-title" style={{ marginBottom: 12 }}>Pending invitations</div>
                {invitations.length === 0 ? <p className="muted-small">No pending invitations.</p> : (
                  <div style={{ display: "grid", gap: 10 }}>
                    {invitations.map((invite) => (
                      <div key={invite.id} style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "center", borderTop: "1px solid var(--border, #e5e7eb)", paddingTop: 12 }}>
                        <div><strong>{invite.email}</strong><div className="muted-small">{invite.role.replace("_", " ")} · Expires {new Date(invite.expires_at).toLocaleDateString()}</div></div>
                        <span className="badge">Pending</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </section>
          )}
        </section>
      </main>
    </div>
  );
}
