"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { apiFetch, API_BASE } from "@/lib/api";
import { getActiveOrganizationId } from "@/lib/organization";

type Organization = { id: string; name: string; timezone: string; role: string };
type Invitation = { id: string; email: string; role: string; expires_at: string; created_at: string };
type Permission = { permission_key: string; category: string; label: string; description: string; sensitive: boolean };
type RoleTemplate = { id: string; role_key: string; name: string; description: string | null; is_system: boolean; is_active: boolean; permissions: Record<string, boolean> };
type TeamMember = { user_id: string; email: string | null; full_name: string | null; role: string; custom_role_id: string | null; custom_role_name: string | null; overrides: Record<string, { effect: "allow" | "deny"; reason?: string | null; expires_at?: string | null }> };
type PermissionData = { permissions: Permission[]; roles: RoleTemplate[]; members: TeamMember[] };
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
  const [permissionData, setPermissionData] = useState<PermissionData | null>(null);
  const [selectedRoleId, setSelectedRoleId] = useState("");
  const [permissionSaving, setPermissionSaving] = useState(false);
  const [permissionMessage, setPermissionMessage] = useState("");
  const [permissionError, setPermissionError] = useState("");
  const [newRoleName, setNewRoleName] = useState("");
  const [newRoleDescription, setNewRoleDescription] = useState("");
  const [roleCreating, setRoleCreating] = useState(false);
  const [selectedMemberId, setSelectedMemberId] = useState("");
  const [selectedMemberRole, setSelectedMemberRole] = useState("");
  const [selectedPermissionKey, setSelectedPermissionKey] = useState("");
  const [overrideEffect, setOverrideEffect] = useState<"allow" | "deny" | "inherit">("inherit");
  const [overrideReason, setOverrideReason] = useState("");

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
          const permissionResponse = await apiFetch(API_BASE + "/api/organizations/" + active.id + "/permissions");
          if (permissionResponse.ok) {
            const permissionResult = await permissionResponse.json() as PermissionData;
            setPermissionData(permissionResult);
            const initialRole = permissionResult.roles.find((role) => role.role_key === "recruiter") || permissionResult.roles[0];
            if (initialRole) setSelectedRoleId(initialRole.id);
            if (permissionResult.members[0]) {
              setSelectedMemberId(permissionResult.members[0].user_id);
              setSelectedMemberRole(permissionResult.members[0].custom_role_id || permissionResult.members[0].role);
            }
            if (permissionResult.permissions[0]) setSelectedPermissionKey(permissionResult.permissions[0].permission_key);
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
  const selectedRole = permissionData?.roles.find((role) => role.id === selectedRoleId) || null;
  const selectedMember = permissionData?.members.find((member) => member.user_id === selectedMemberId) || null;

  async function saveRolePermissions() {
    if (!organization || !selectedRole) return;
    setPermissionSaving(true); setPermissionMessage(""); setPermissionError("");
    try {
      const response = await apiFetch(API_BASE + "/api/organizations/" + organization.id + "/roles/" + selectedRole.id + "/permissions", {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ permissions: selectedRole.permissions }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail || "Unable to save role permissions.");
      setPermissionMessage("Permissions saved for " + selectedRole.name + ".");
    } catch (cause) {
      setPermissionError(cause instanceof Error ? cause.message : "Unable to save permissions.");
    } finally { setPermissionSaving(false); }
  }

  async function createCustomRole(event: FormEvent) {
    event.preventDefault();
    if (!organization) return;
    setRoleCreating(true); setPermissionMessage(""); setPermissionError("");
    try {
      const response = await apiFetch(API_BASE + "/api/organizations/" + organization.id + "/roles", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newRoleName, description: newRoleDescription || null }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail || "Unable to create custom role.");
      const refreshed = await apiFetch(API_BASE + "/api/organizations/" + organization.id + "/permissions");
      if (refreshed.ok) {
        const data = await refreshed.json() as PermissionData;
        setPermissionData(data);
        setSelectedRoleId(body.role.id);
      }
      setNewRoleName(""); setNewRoleDescription("");
      setPermissionMessage("Custom role created. Configure its permissions before assigning it.");
    } catch (cause) {
      setPermissionError(cause instanceof Error ? cause.message : "Unable to create custom role.");
    } finally { setRoleCreating(false); }
  }

  async function saveMemberRole() {
    if (!organization || !selectedMember) return;
    setPermissionSaving(true); setPermissionMessage(""); setPermissionError("");
    try {
      const custom = selectedMemberRole.startsWith("custom:");
      const response = await apiFetch(API_BASE + "/api/organizations/" + organization.id + "/members/" + selectedMember.user_id + "/role", {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(custom ? { custom_role_id: selectedMemberRole.slice(7) } : { role: selectedMemberRole }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail || "Unable to update member role.");
      const refreshed = await apiFetch(API_BASE + "/api/organizations/" + organization.id + "/permissions");
      if (refreshed.ok) setPermissionData(await refreshed.json() as PermissionData);
      setPermissionMessage("Team member role updated.");
    } catch (cause) {
      setPermissionError(cause instanceof Error ? cause.message : "Unable to update member role.");
    } finally { setPermissionSaving(false); }
  }

  async function saveMemberOverride() {
    if (!organization || !selectedMember || !selectedPermissionKey) return;
    setPermissionSaving(true); setPermissionMessage(""); setPermissionError("");
    try {
      const response = await apiFetch(API_BASE + "/api/organizations/" + organization.id + "/members/" + selectedMember.user_id + "/permissions/" + encodeURIComponent(selectedPermissionKey), {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ effect: overrideEffect, reason: overrideReason || null }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail || "Unable to update member permission.");
      const refreshed = await apiFetch(API_BASE + "/api/organizations/" + organization.id + "/permissions");
      if (refreshed.ok) setPermissionData(await refreshed.json() as PermissionData);
      setPermissionMessage("Individual permission updated.");
    } catch (cause) {
      setPermissionError(cause instanceof Error ? cause.message : "Unable to update member permission.");
    } finally { setPermissionSaving(false); }
  }

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
          {organization && permissionData && (
            <section className="card" style={{ maxWidth: 1100, marginTop: 20 }}>
              <div className="card-head"><span className="card-title">Roles & permissions</span><span className="badge blue">Granular access control</span></div>
              <p className="muted-small" style={{ lineHeight: 1.6 }}>Configure organisation-wide role templates, create custom roles, and grant or revoke individual permissions. Changes are recorded in the audit history.</p>
              {permissionMessage && <p className="notice" role="status">{permissionMessage}</p>}
              {permissionError && <p className="dashboard-error" role="alert">{permissionError}</p>}
              <div style={{ display: "grid", gridTemplateColumns: "minmax(220px, 280px) minmax(0, 1fr)", gap: 20, marginTop: 18 }}>
                <div style={{ display: "grid", alignContent: "start", gap: 12 }}>
                  <label style={{ display: "grid", gap: 7, fontSize: 13, fontWeight: 650 }}>Role template
                    <select className="filter" value={selectedRoleId} onChange={(event) => setSelectedRoleId(event.target.value)}>
                      {permissionData.roles.map((role) => <option key={role.id} value={role.id}>{role.name}{role.is_system ? " · Standard" : " · Custom"}</option>)}
                    </select>
                  </label>
                  {selectedRole && <div className="muted-small">{selectedRole.description || "Custom organisation role"}</div>}
                  <form onSubmit={createCustomRole} style={{ display: "grid", gap: 8, borderTop: "1px solid var(--border, #e5e7eb)", paddingTop: 14 }}>
                    <strong style={{ fontSize: 14 }}>Create custom role</strong>
                    <input className="filter" required minLength={2} maxLength={80} value={newRoleName} onChange={(event) => setNewRoleName(event.target.value)} placeholder="e.g. Senior Recruiter" />
                    <input className="filter" maxLength={300} value={newRoleDescription} onChange={(event) => setNewRoleDescription(event.target.value)} placeholder="Short description (optional)" />
                    <button className="btn" disabled={roleCreating}>{roleCreating ? "Creating…" : "Create role"}</button>
                  </form>
                </div>
                <div>
                  {selectedRole && <div style={{ display: "grid", gap: 8 }}>
                    {permissionData.permissions.map((permission) => (
                      <label key={permission.permission_key} style={{ display: "flex", gap: 10, alignItems: "flex-start", padding: "9px 0", borderBottom: "1px solid var(--border, #e5e7eb)", fontSize: 13 }}>
                        <input type="checkbox" checked={Boolean(selectedRole.permissions[permission.permission_key])} disabled={selectedRole.role_key === "owner" || selectedRole.role_key === "admin" && organization.role !== "owner"} onChange={(event) => setPermissionData((current) => current ? ({ ...current, roles: current.roles.map((role) => role.id === selectedRole.id ? { ...role, permissions: { ...role.permissions, [permission.permission_key]: event.target.checked } } : role) }) : current)} />
                        <span style={{ display: "grid", gap: 2 }}><strong>{permission.label}{permission.sensitive ? " · Sensitive" : ""}</strong><span className="muted-small">{permission.description}</span><span className="muted-small">{permission.category}</span></span>
                      </label>
                    ))}
                    <div className="modal-actions" style={{ justifyContent: "flex-start" }}>
                      <button className="btn primary" disabled={permissionSaving || selectedRole.role_key === "owner" || selectedRole.role_key === "admin" && organization.role !== "owner"} onClick={saveRolePermissions}>{permissionSaving ? "Saving…" : "Save role permissions"}</button>
                    </div>
                  </div>}
                </div>
              </div>
              <div style={{ borderTop: "1px solid var(--border, #e5e7eb)", marginTop: 24, paddingTop: 18 }}>
                <strong>Team member access</strong>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12, marginTop: 12 }}>
                  <label style={{ display: "grid", gap: 7, fontSize: 13, fontWeight: 650 }}>Team member
                    <select className="filter" value={selectedMemberId} onChange={(event) => {
                      setSelectedMemberId(event.target.value);
                      const member = permissionData.members.find((item) => item.user_id === event.target.value);
                      setSelectedMemberRole(member?.custom_role_id ? "custom:" + member.custom_role_id : member?.role || "");
                    }}>
                      {permissionData.members.map((member) => <option key={member.user_id} value={member.user_id}>{member.full_name || member.email || member.user_id}{member.role === "owner" ? " · Owner" : ""}</option>)}
                    </select>
                  </label>
                  <label style={{ display: "grid", gap: 7, fontSize: 13, fontWeight: 650 }}>Assigned role
                    <select className="filter" value={selectedMemberRole} onChange={(event) => setSelectedMemberRole(event.target.value)} disabled={selectedMember?.role === "owner"}>
                      <optgroup label="Standard roles">
                        {["admin", "recruiter", "hiring_manager", "viewer"].map((role) => <option key={role} value={role}>{role.replace("_", " ")}</option>)}
                      </optgroup>
                      <optgroup label="Custom roles">
                        {permissionData.roles.filter((role) => !role.is_system).map((role) => <option key={role.id} value={"custom:" + role.id}>{role.name}</option>)}
                      </optgroup>
                    </select>
                  </label>
                  <div style={{ display: "flex", alignItems: "end" }}><button className="btn" disabled={permissionSaving || !selectedMember || selectedMember.role === "owner"} onClick={saveMemberRole}>Update role</button></div>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12, marginTop: 16 }}>
                  <label style={{ display: "grid", gap: 7, fontSize: 13, fontWeight: 650 }}>Permission
                    <select className="filter" value={selectedPermissionKey} onChange={(event) => setSelectedPermissionKey(event.target.value)}>
                      {permissionData.permissions.map((permission) => <option key={permission.permission_key} value={permission.permission_key}>{permission.label}</option>)}
                    </select>
                  </label>
                  <label style={{ display: "grid", gap: 7, fontSize: 13, fontWeight: 650 }}>Individual override
                    <select className="filter" value={overrideEffect} onChange={(event) => setOverrideEffect(event.target.value as "allow" | "deny" | "inherit")}>
                      <option value="inherit">Use role default</option><option value="allow">Grant access</option><option value="deny">Deny access</option>
                    </select>
                  </label>
                  <label style={{ display: "grid", gap: 7, fontSize: 13, fontWeight: 650 }}>Reason (optional)
                    <input className="filter" maxLength={500} value={overrideReason} onChange={(event) => setOverrideReason(event.target.value)} placeholder="Why is this access changing?" />
                  </label>
                  <div style={{ display: "flex", alignItems: "end" }}><button className="btn primary" disabled={permissionSaving || !selectedMember || selectedMember.role === "owner"} onClick={saveMemberOverride}>Save individual access</button></div>
                </div>
                {selectedMember && <p className="muted-small" style={{ marginTop: 12 }}>Current overrides: {Object.keys(selectedMember.overrides || {}).length}. Active overrides take precedence over the role template. The Owner's access cannot be overridden.</p>}
              </div>
            </section>
          )}
        </section>
      </main>
    </div>
  );
}
