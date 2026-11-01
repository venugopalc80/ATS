"use client";

import { useCallback, useEffect, useState } from "react";
import { API_BASE, apiFetch } from "@/lib/api";
import { getActiveOrganizationId } from "@/lib/organization";

export type SavedReportType = "kpis" | "funnel" | "workload" | "sources" | "forecast" | "campaign_roi";
export type SavedReport = {
  id: string;
  name: string;
  description?: string | null;
  report_type: SavedReportType;
  filters: { date_from?: string; date_to?: string; job_id?: string; recruiter_id?: string };
  is_shared: boolean;
  created_by: string;
  can_manage: boolean;
};
type Props = {
  reportType: SavedReportType;
  dateFrom: string;
  dateTo: string;
  onApply: (report: SavedReport) => void;
};

function label(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export default function SavedReports({ reportType, dateFrom, dateTo, onApply }: Props) {
  const [organizationId, setOrganizationId] = useState("");
  const [reports, setReports] = useState<SavedReport[]>([]);
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    setOrganizationId(getActiveOrganizationId() || "");
  }, []);

  const load = useCallback(async () => {
    if (!API_BASE || !organizationId) return;
    setLoading(true);
    setError("");
    try {
      const response = await apiFetch(
        API_BASE + "/api/analytics/reports?organization_id=" + encodeURIComponent(organizationId)
      );
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || "Could not load saved reports.");
      setReports(await response.json());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load saved reports.");
    } finally {
      setLoading(false);
    }
  }, [organizationId]);

  useEffect(() => {
    if (organizationId) void load();
  }, [organizationId, load]);

  async function save() {
    const cleaned = name.trim();
    if (!cleaned || !organizationId || !API_BASE) {
      setError("Analytics API or organisation configuration is missing.");
      return;
    }
    setSaving(true);
    setError("");
    setMessage("");
    const filters: Record<string, string> = {};
    if (!["workload", "forecast"].includes(reportType)) {
      if (dateFrom) filters.date_from = dateFrom;
      if (dateTo) filters.date_to = dateTo;
    }
    try {
      const response = await apiFetch(
        API_BASE + "/api/analytics/reports?organization_id=" + encodeURIComponent(organizationId),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: cleaned, report_type: reportType, filters }),
        }
      );
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || "Could not save this report.");
      setName("");
      setMessage("Report saved privately to your account in this organisation.");
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save this report.");
    } finally {
      setSaving(false);
    }
  }

  async function remove(report: SavedReport) {
    if (!organizationId || !API_BASE) return;
    setError("");
    setMessage("");
    try {
      const response = await apiFetch(
        API_BASE + "/api/analytics/reports/" + report.id + "?organization_id=" + encodeURIComponent(organizationId),
        { method: "DELETE" }
      );
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || "Could not delete this report.");
      setMessage("Saved report deleted.");
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not delete this report.");
    }
  }

  return (
    <section className="card analytics-saved-reports" aria-label="Saved reports">
      <div className="card-head">
        <div>
          <div className="card-title">Saved reports</div>
          <div className="muted-small">Save a report setup and reuse its report type and date filters later.</div>
        </div>
        <span className="muted-small">{reports.length} saved</span>
      </div>
      <div className="analytics-saved-report-create">
        <label className="analytics-saved-report-name">
          <span className="muted-small">Name this report</span>
          <input className="filter" value={name} maxLength={100} placeholder="e.g. Monthly hiring funnel" onChange={(event) => setName(event.target.value)} />
        </label>
        <div className="analytics-saved-report-action">
          <span className="muted-small">{label(reportType)} · {["workload", "forecast"].includes(reportType) ? "Snapshot / baseline filters" : dateFrom || "Any start"} to {["workload", "forecast"].includes(reportType) ? "not applicable" : dateTo || "Any end"}</span>
          <button className="btn primary" type="button" disabled={saving || !name.trim() || !organizationId || !API_BASE} onClick={() => void save()}>
            {saving ? "Saving…" : "Save current setup"}
          </button>
        </div>
      </div>
      {error && <div className="notice mt-3" role="alert">{error}</div>}
      {message && <div className="notice mt-3" role="status">{message}</div>}
      {loading ? <p className="muted-small mt-3">Loading saved reports…</p> : reports.length ? (
        <div className="analytics-saved-report-list" aria-live="polite">
          {reports.map((report) => (
            <div className="analytics-saved-report-row" key={report.id}>
              <div>
                <strong>{report.name}</strong>
                <div className="muted-small">{label(report.report_type)} · {report.is_shared ? "Shared with organisation" : "Private"} · {report.filters?.date_from || "Any start"} to {report.filters?.date_to || "Any end"}</div>
              </div>
              <div className="analytics-saved-report-buttons">
                <button className="btn" type="button" onClick={() => onApply(report)}>Apply</button>
                {report.can_manage && <button className="btn" type="button" onClick={() => void remove(report)} aria-label={"Delete " + report.name}>Delete</button>}
              </div>
            </div>
          ))}
        </div>
      ) : <p className="muted-small mt-3">No saved reports yet. Save the current report setup to reuse it later.</p>}
    </section>
  );
}
