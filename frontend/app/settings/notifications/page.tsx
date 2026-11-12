"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";
const DEFAULT_ORG = process.env.NEXT_PUBLIC_ORGANIZATION_ID ?? "";
const TYPES = [
  { key: "interview_reminder", label: "Interview reminders" },
  { key: "recruiter_assignment", label: "Recruiter assignments" },
  { key: "overdue_feedback", label: "Overdue interview feedback" },
  { key: "application_update", label: "Application updates" },
] as const;
const CHANNELS = [
  { key: "in_app", label: "In-app" },
  { key: "email", label: "Email" },
  { key: "sms", label: "SMS" },
] as const;

type Preference = { notification_type: string; channel: string; enabled: boolean };

export default function NotificationSettingsPage() {
  const [organizationId, setOrganizationId] = useState(DEFAULT_ORG);
  const [preferences, setPreferences] = useState<Preference[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    const stored = window.localStorage.getItem("aqerith_active_org") || window.localStorage.getItem("talentos_active_org");
    if (stored) setOrganizationId(stored);
  }, []);

  const load = useCallback(async () => {
    if (!organizationId) {
      setLoading(false);
      setError("Select an active organisation before editing notification preferences.");
      return;
    }
    setError("");
    try {
      const q = new URLSearchParams({ organization_id: organizationId });
      const response = await apiFetch(`${API_BASE}/api/notification-preferences?${q}`);
      if (!response.ok) throw new Error("Unable to load notification preferences.");
      setPreferences((await response.json()) as Preference[]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to load preferences.");
    } finally {
      setLoading(false);
    }
  }, [organizationId]);

  useEffect(() => {
    void load();
  }, [load]);

  function enabled(type: string, channel: string) {
    return preferences.find((p) => p.notification_type === type && p.channel === channel)?.enabled ?? true;
  }

  async function update(type: string, channel: string, value: boolean) {
    setSaving(`${type}:${channel}`);
    setError("");
    setNotice("");
    try {
      const response = await apiFetch(`${API_BASE}/api/notification-preferences`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          organization_id: organizationId,
          notification_type: type,
          channel,
          enabled: value,
        }),
      });
      if (!response.ok) throw new Error("Unable to save this preference.");
      const saved = (await response.json()) as Preference;
      setPreferences((current) => [
        ...current.filter((p) => !(p.notification_type === type && p.channel === channel)),
        saved,
      ]);
      setNotice("Notification preference saved.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to save preference.");
    } finally {
      setSaving("");
    }
  }

  return (
    <main className="shell">
      <section className="main">
        <div className="content">
          <p className="eyebrow">Account settings</p>
          <h1>Notification preferences</h1>
          <p className="subtitle">Choose which non-essential recruitment updates you receive and through which channel.</p>
          <p className="muted-small mt-2">Security, account recovery and critical service notices remain enabled.</p>
          {error && <p role="alert" className="notice mt-4">{error}</p>}
          {notice && <p role="status" className="notice mt-4">{notice}</p>}
          {loading ? <p className="mt-6">Loading preferences…</p> : (
            <div className="card mt-6 overflow-x-auto">
              <table className="table">
                <thead><tr><th scope="col">Notification</th>{CHANNELS.map((channel) => <th scope="col" key={channel.key}>{channel.label}</th>)}</tr></thead>
                <tbody>
                  {TYPES.map((type) => (
                    <tr key={type.key}>
                      <th scope="row">{type.label}</th>
                      {CHANNELS.map((channel) => (
                        <td key={channel.key}>
                          <label className="inline-flex items-center gap-2">
                            <input
                              type="checkbox"
                              checked={enabled(type.key, channel.key)}
                              disabled={Boolean(saving)}
                              onChange={(event) => void update(type.key, channel.key, event.target.checked)}
                              aria-label={`${type.label} via ${channel.label}`}
                            />
                            <span className="sr-only">{enabled(type.key, channel.key) ? "Enabled" : "Disabled"}</span>
                          </label>
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
