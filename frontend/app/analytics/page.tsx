"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { API_BASE, apiFetch } from "@/lib/api";
import { getActiveOrganizationId } from "@/lib/organization";

type Metric = { value: number | null; status?: string; numerator?: number; denominator?: number; complete_records?: number; complete_requisitions?: number; definition?: string };
type Kpis = { metrics: Record<string, Metric & { median_days_open?: number | null; open_more_than_30_days?: number; missing_opened_at?: number }>; filters: { date_from: string | null; date_to: string | null } };
type Funnel = {
  sample_size: number;
  low_sample_size: boolean;
  stages: Array<{ stage: string; stage_visits: number; distinct_applications: number }>;
  stage_conversions: Array<{ stage: string; next_stage: string; entered_applications: number; reached_next_applications: number; conversion_rate: number | null }>;
  stage_waiting_time: Array<{ stage: string; completed_intervals: number; median_days: number | null; p75_days: number | null; p90_days: number | null }>;
  outcomes: Record<string, number>;
  limitations: string[];
};
type Workload = { recruiters: Array<{ user_id: string; name: string; role: string; open_vacancies: number; on_hold_vacancies: number; active_applications: number; upcoming_interviews: number; open_tasks: number; overdue_tasks: number }>; unassigned: { unassigned_open_vacancies: number; unassigned_open_tasks: number }; definitions: { note: string } };
type Source = { source: string; applications: number; qualified_applications: number; completed_interviews: number; offers: number; decided_offers: number; accepted_offers: number; hires: number; offer_acceptance_rate: number | null; conversion_rate: number | null; sample_warning: boolean };
type Sources = { sources: Source[]; limitations: string[] };
type CampaignChannel = { campaign_id: string; campaign_name: string; campaign_status: string; budget_amount: number | null; budget_currency: string | null; channel_id: string; channel_key: string; source_label: string | null; spend_amount: number | null; spend_currency: string | null; applications: number; hires: number; applications_with_accepted_offer: number; cost_per_application: number | null; cost_per_hire: number | null; sample_warning: boolean; financial_roi: number | null; financial_roi_status: string };
type CampaignROI = { campaign_channels: CampaignChannel[]; limitations: string[] };
type Forecast = {
  history_months: number;
  history: Array<{ month: string; approved_headcount: number; approved_requisitions: number }>;
  forecast: { month: string; expected_approved_headcount: number | null; pending_approval_headcount: number; pending_approval_requisitions: number; trend: string; confidence: string; status: string };
  methodology: { baseline: string; trend: string; confidence: string; exclusions: string[] };
};

function isoDate(daysAgo = 0) {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  return [d.getFullYear(), String(d.getMonth() + 1).padStart(2, "0"), String(d.getDate()).padStart(2, "0")].join("-");
}
function nice(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
function number(value: number | null | undefined, digits = 0) {
  if (value == null || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value);
}
function percent(value: number | null | undefined) {
  return value == null ? "—" : new Intl.NumberFormat(undefined, { style: "percent", maximumFractionDigits: 1 }).format(value);
}

export default function AnalyticsPage() {
  const [dateFrom, setDateFrom] = useState(isoDate(30));
  const [dateTo, setDateTo] = useState(isoDate());
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [funnel, setFunnel] = useState<Funnel | null>(null);
  const [workload, setWorkload] = useState<Workload | null>(null);
  const [sources, setSources] = useState<Sources | null>(null);
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [campaignROI, setCampaignROI] = useState<CampaignROI | null>(null);
  const [loading, setLoading] = useState(true);
  const [reportType, setReportType] = useState("kpis");
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const organizationId = getActiveOrganizationId();
    if (!API_BASE || !organizationId) {
      setError("Analytics configuration is missing. Select an organisation and confirm the API URL.");
      setLoading(false);
      return;
    }
    if (dateFrom && dateTo && dateFrom > dateTo) {
      setError("The start date must be on or before the end date.");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    const params = new URLSearchParams({ organization_id: organizationId });
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    try {
      const paths = [
        "/api/analytics/kpis?" + params.toString(),
        "/api/analytics/funnel?" + params.toString(),
        "/api/analytics/workload?organization_id=" + encodeURIComponent(organizationId),
        "/api/analytics/sources?" + params.toString(),
        "/api/analytics/forecast?organization_id=" + encodeURIComponent(organizationId),
        "/api/analytics/campaign-roi?" + params.toString(),
      ];
      const responses = await Promise.all(paths.map((path) => apiFetch(API_BASE + path)));
      const failed = responses.find((response) => !response.ok);
      if (failed) {
        if (failed.status === 401) throw new Error("Your session has expired. Sign in again.");
        if (failed.status === 403) throw new Error("You don't have access to this organisation's analytics.");
        if (failed.status === 503) throw new Error("Analytics data is temporarily unavailable. Please retry.");
        throw new Error("Analytics could not be loaded (HTTP " + failed.status + ").");
      }
      const [k, f, w, s, forecastData, campaignData] = await Promise.all(responses.map((response) => response.json()));
      setKpis(k);
      setFunnel(f);
      setWorkload(w);
      setSources(s);
      setForecast(forecastData);
      setCampaignROI(campaignData);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load analytics.");
    } finally {
      setLoading(false);
    }
  }, [dateFrom, dateTo]);

  useEffect(() => { void load(); }, [load]);

  async function exportReport() {
    const organizationId = getActiveOrganizationId();
    if (!API_BASE || !organizationId) {
      setError("Analytics configuration is missing. Select an organisation and confirm the API URL.");
      return;
    }
    setExporting(true);
    setError("");
    try {
      const params = new URLSearchParams({ organization_id: organizationId, report_type: reportType });
      if (dateFrom) params.set("date_from", dateFrom);
      if (dateTo) params.set("date_to", dateTo);
      const response = await apiFetch(API_BASE + "/api/analytics/export?" + params.toString());
      if (!response.ok) throw new Error("Report export failed (HTTP " + response.status + ").");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "aqerith-" + reportType + "-report.csv";
      link.click();
      URL.revokeObjectURL(url);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to export report.");
    } finally {
      setExporting(false);
    }
  }

  function exportSources() {
    if (!sources?.sources.length) return;
    const headers = ["Source", "Applications", "Qualified applications", "Completed interviews", "Offers", "Decided offers", "Accepted offers", "Hires", "Offer acceptance rate", "Application-to-hire rate"];
    const rows = sources.sources.map((s) => [s.source, s.applications, s.qualified_applications, s.completed_interviews, s.offers, s.decided_offers, s.accepted_offers, s.hires, s.offer_acceptance_rate ?? "", s.conversion_rate ?? ""]);
    const csv = [headers, ...rows].map((row) => row.map((cell) => {
      const text = String(cell);
      const safe = typeof cell === "string" && /^\s*[=+\-@]/.test(text) ? "'" + text : text;
      return '"' + safe.replaceAll('"', '""') + '"';
    }).join(",")).join("\r\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "aqerith-source-effectiveness.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  const metrics = kpis?.metrics;
  const cards = [
    { key: "applications", label: "Applications", value: number(metrics?.applications?.value), note: "Created in selected period" },
    { key: "active_applications", label: "Active applications", value: number(metrics?.active_applications?.value), note: "Current status snapshot for cohort" },
    { key: "offer_acceptance_rate", label: "Offer acceptance", value: percent(metrics?.offer_acceptance_rate?.value), note: (metrics?.offer_acceptance_rate?.numerator ?? 0) + " accepted of " + (metrics?.offer_acceptance_rate?.denominator ?? 0) + " decided" },
    { key: "median_time_to_hire_days", label: "Median time to hire", value: metrics?.median_time_to_hire_days?.value == null ? "—" : number(metrics.median_time_to_hire_days.value, 1) + " days", note: (metrics?.median_time_to_hire_days?.complete_records ?? 0) + " complete records" },
    { key: "median_time_to_fill_days", label: "Median time to fill", value: metrics?.median_time_to_fill_days?.value == null ? "—" : number(metrics.median_time_to_fill_days.value, 1) + " days", note: (metrics?.median_time_to_fill_days?.complete_requisitions ?? 0) + " complete requisitions" },
    { key: "open_vacancies", label: "Open vacancies", value: number(metrics?.open_vacancies?.value), note: "Current snapshot" },
    { key: "vacancy_ageing", label: "Vacancies open 30+ days", value: number(metrics?.vacancy_ageing?.open_more_than_30_days), note: "Age anchored to opened date or job creation" },
  ];

  return (
    <div className="shell">
      <aside className="sidebar">
        <Link href="/dashboard" className="brand">AQERITH</Link>
        <div className="nav-label">Workspace</div>
        {[
          ["Dashboard", "/dashboard", "⌂"], ["Jobs", "/jobs", "▣"], ["Candidates", "/candidates", "♙"],
          ["Submissions", "/submissions", "↗"], ["Interviews", "/interviews", "◷"], ["Clients", "/clients", "□"],
          ["Onboarding", "/onboarding", "✓"], ["Offers", "/offers", "＄"], ["Placements", "/placements", "◈"],
          ["Analytics", "/analytics", "▥"],
        ].map(([label, href, symbol]) => (
          <Link key={label} href={href} className={"nav-item" + (label === "Analytics" ? " active" : "")}>
            <span aria-hidden="true">{symbol}</span><span>{label}</span>
          </Link>
        ))}
        <div className="nav-label">Administration</div>
        <Link href="/dashboard" className="nav-item"><span aria-hidden="true">⚙</span><span>Settings</span></Link>
        <div className="nav-item"><span aria-hidden="true">?</span><span>Help &amp; support</span></div>
      </aside>
      <div className="main">
        <header className="topbar">
          <div><strong>Analytics &amp; intelligence</strong><div className="muted-small">Recruitment performance, funnel health and workload</div></div>
          <Link href="/dashboard" className="btn">Back to dashboard</Link>
        </header>
        <main className="content analytics-content">
          <div className="header-row analytics-header">
            <div><div className="eyebrow">Reporting</div><h1>Recruitment analytics</h1><p className="subtitle">A measurable view of hiring performance, with explicit cohorts and honest gaps.</p></div>
            <div className="actions analytics-header-actions">
              <select className="filter" aria-label="Report to export" value={reportType} onChange={(event) => setReportType(event.target.value)}>
                <option value="kpis">KPI report</option><option value="funnel">Funnel report</option><option value="workload">Workload report</option><option value="sources">Source report</option><option value="forecast">Forecast report</option><option value="campaign_roi">Campaign efficiency report</option>
              </select>
              <button className="btn" onClick={() => void exportReport()} disabled={exporting}>{exporting ? "Exporting…" : "Export CSV"}</button>
              <button className="btn" onClick={() => void load()} disabled={loading}>{loading ? "Refreshing…" : "Refresh data"}</button>
            </div>
          </div>
          <section className="card analytics-filter-card">
            <div className="analytics-filter-copy"><strong>Reporting period</strong><span className="muted-small">Application and stage-event cohorts use the selected dates. Vacancy and workload figures are current snapshots.</span></div>
            <div className="analytics-filter-controls">
              <label>From<input className="filter" type="date" value={dateFrom} max={dateTo || undefined} onChange={(event) => setDateFrom(event.target.value)} /></label>
              <label>To<input className="filter" type="date" value={dateTo} min={dateFrom || undefined} onChange={(event) => setDateTo(event.target.value)} /></label>
              <button className="btn primary" onClick={() => void load()} disabled={loading}>Apply filters</button>
            </div>
          </section>
          {error && <div className="dashboard-error" role="alert"><div><strong>Analytics unavailable</strong><p>{error}</p></div><button className="btn" onClick={() => void load()}>Try again</button></div>}
          {loading && !kpis ? <div className="analytics-kpi-grid">{Array.from({ length: 7 }).map((_, index) => <div className="card" key={index}><span className="dashboard-skeleton" /><div className="dashboard-loading-lines"><span /><span /></div></div>)}</div> : null}
          {kpis && <section className="analytics-kpi-grid" aria-label="Recruitment KPIs">
            {cards.map((card) => <article className="card analytics-kpi" key={card.key}><div className="metric-title">{card.label}</div><div className="metric-value">{loading ? "…" : card.value}</div><div className="metric-foot analytics-foot">{card.note}</div></article>)}
          </section>}
          {forecast && <section className="card analytics-forecast-card">
            <div className="card-head">
              <div><div className="card-title">Hiring demand forecast</div><div className="muted-small">Next calendar month · transparent baseline, not an AI prediction</div></div>
              <span className={"badge " + (forecast.forecast.confidence === "unavailable" ? "amber" : "blue")}>{nice(forecast.forecast.confidence)} confidence</span>
            </div>
            <div className="analytics-forecast-summary">
              <div><div className="metric-title">Expected approved headcount</div><div className="metric-value">{forecast.forecast.expected_approved_headcount == null ? "—" : number(forecast.forecast.expected_approved_headcount, 1)}</div><div className="muted-small">{forecast.forecast.status === "no_historical_approved_requisitions" ? "Not enough historical approved requisitions to estimate demand." : "Six-month average including zero-activity months."}</div></div>
              <div><div className="metric-title">Pending approval</div><div className="metric-value">{number(forecast.forecast.pending_approval_headcount)}</div><div className="muted-small">{number(forecast.forecast.pending_approval_requisitions)} requisitions awaiting a decision</div></div>
              <div><div className="metric-title">Historical trend</div><div className="metric-value analytics-trend">{nice(forecast.forecast.trend)}</div><div className="muted-small">First three months compared with latest three</div></div>
            </div>
            <div className="analytics-history-bars">
              {forecast.history.map((month) => {
                const maximum = Math.max(1, ...forecast.history.map((item) => item.approved_headcount));
                const monthLabel = new Intl.DateTimeFormat(undefined, { month: "short", year: "2-digit" }).format(new Date(month.month + "T12:00:00"));
                return <div className="analytics-history-item" key={month.month}><div className="analytics-history-value">{number(month.approved_headcount)}</div><div className="analytics-history-track"><div className="analytics-history-fill" style={{ height: Math.max(3, month.approved_headcount / maximum * 100) + "%" }} /></div><div className="analytics-history-label">{monthLabel}</div></div>;
              })}
            </div>
            <details className="analytics-details"><summary>How this forecast is calculated</summary><p>{forecast.methodology.baseline}</p><p>{forecast.methodology.trend}</p><p>{forecast.methodology.confidence}</p><p>Excluded: {forecast.methodology.exclusions.join(", ")}.</p></details>
          </section>}
          <div className="analytics-two-col">
            <section className="card">
              <div className="card-head"><div><div className="card-title">Recruitment funnel</div><div className="muted-small">Recorded stage events, not all applications</div></div><span className={"badge " + (funnel?.low_sample_size ? "amber" : "blue")}>{number(funnel?.sample_size)} in cohort</span></div>
              {funnel?.low_sample_size && <div className="notice">Small sample: interpret conversion percentages cautiously.</div>}
              {!funnel?.stage_conversions.length && <div className="analytics-empty">No stage transition history is available for this period.</div>}
              {funnel?.stage_conversions.map((stage) => <div className="analytics-conversion" key={stage.stage}><div className="analytics-conversion-head"><strong>{nice(stage.stage)} <span>→ {nice(stage.next_stage)}</span></strong><span>{percent(stage.conversion_rate)}</span></div><div className="analytics-bar-track"><div className="analytics-bar-fill" style={{ width: Math.max(0, Math.min(100, (stage.conversion_rate ?? 0) * 100)) + "%" }} /></div><div className="muted-small">{number(stage.reached_next_applications)} of {number(stage.entered_applications)} applications later reached the next stage</div></div>)}
              <div className="analytics-subsection"><strong>Stage visits</strong>{funnel?.stages.map((stage) => <div className="analytics-simple-row" key={stage.stage}><span>{nice(stage.stage)}</span><strong>{number(stage.distinct_applications)} applications <small>· {number(stage.stage_visits)} visits</small></strong></div>)}</div>
            </section>
            <section className="card">
              <div className="card-head"><div><div className="card-title">Time in stage</div><div className="muted-small">Completed intervals only; open intervals are excluded</div></div></div>
              {!funnel?.stage_waiting_time.length && <div className="analytics-empty">No completed stage intervals are available yet.</div>}
              {funnel?.stage_waiting_time.map((stage) => <div className="analytics-wait-row" key={stage.stage}><div><strong>{nice(stage.stage)}</strong><div className="muted-small">{number(stage.completed_intervals)} completed intervals</div></div><div className="analytics-wait-stats"><span><strong>{number(stage.median_days, 1)}</strong><small>Median days</small></span><span><strong>{number(stage.p75_days, 1)}</strong><small>P75</small></span><span><strong>{number(stage.p90_days, 1)}</strong><small>P90</small></span></div></div>)}
              <div className="analytics-subsection"><strong>Current recorded outcomes</strong>{Object.entries(funnel?.outcomes ?? {}).map(([status, count]) => <div className="analytics-simple-row" key={status}><span>{nice(status)}</span><strong>{number(count)}</strong></div>)}</div>
              {funnel?.limitations.length ? <details className="analytics-details"><summary>Metric notes and limitations</summary><ul>{funnel.limitations.map((item) => <li key={item}>{item}</li>)}</ul></details> : null}
            </section>
          </div>
          <section className="card analytics-table-card">
            <div className="card-head"><div><div className="card-title">Recruiter workload</div><div className="muted-small">{workload?.definitions.note ?? "Workload counts are not productivity scores."}</div></div></div>
            <div className="analytics-table-wrap"><table className="table"><thead><tr><th>Recruiter / member</th><th>Open vacancies</th><th>On hold</th><th>Active applications</th><th>Upcoming interviews</th><th>Open tasks</th><th>Overdue</th></tr></thead><tbody>
              {workload?.recruiters.map((person) => <tr key={person.user_id}><td><strong>{person.name}</strong><div className="muted-small">{nice(person.role)}</div></td><td>{number(person.open_vacancies)}</td><td>{number(person.on_hold_vacancies)}</td><td>{number(person.active_applications)}</td><td>{number(person.upcoming_interviews)}</td><td>{number(person.open_tasks)}</td><td><span className={person.overdue_tasks ? "analytics-overdue" : ""}>{number(person.overdue_tasks)}</span></td></tr>)}
              {!workload?.recruiters.length && <tr><td colSpan={7}>No organisation members returned for this workspace.</td></tr>}
            </tbody></table></div>
            <div className="analytics-unassigned"><span>Unassigned open vacancies <strong>{number(workload?.unassigned.unassigned_open_vacancies)}</strong></span><span>Unassigned open tasks <strong>{number(workload?.unassigned.unassigned_open_tasks)}</strong></span></div>
          </section>
          <section className="card analytics-table-card">
            <div className="card-head"><div><div className="card-title">Source effectiveness</div><div className="muted-small">Current status outcomes grouped by application source; association does not prove causation.</div></div><button className="btn" onClick={exportSources} disabled={!sources?.sources.length}>Export CSV</button></div>
            <div className="analytics-table-wrap"><table className="table"><thead><tr><th>Source</th><th>Applications</th><th>Qualified</th><th>Interviews</th><th>Offers</th><th>Accepted / decided</th><th>Hires</th><th>App → hire</th></tr></thead><tbody>
              {sources?.sources.map((source) => <tr key={source.source}><td><strong>{source.source}</strong>{source.sample_warning && <div className="muted-small analytics-sample-warning">Small sample (&lt;5)</div>}</td><td>{number(source.applications)}</td><td>{number(source.qualified_applications)}</td><td>{number(source.completed_interviews)}</td><td>{number(source.offers)}</td><td>{number(source.accepted_offers)} / {number(source.decided_offers)} <div className="muted-small">{percent(source.offer_acceptance_rate)}</div></td><td>{number(source.hires)}</td><td>{percent(source.conversion_rate)}</td></tr>)}
              {!sources?.sources.length && <tr><td colSpan={8}>No source-attributed applications are available for this period.</td></tr>}
            </tbody></table></div>
            {sources?.limitations.length ? <details className="analytics-details"><summary>Source metric notes</summary><ul>{sources.limitations.map((item) => <li key={item}>{item}</li>)}</ul></details> : null}
          </section>
          <section className="card analytics-table-card">
            <div className="card-head"><div><div className="card-title">Campaign spend efficiency</div><div className="muted-small">Spend is a current snapshot; cost ratios are shown only for all-time attribution. Financial ROI needs revenue data.</div></div></div>
            <div className="analytics-table-wrap"><table className="table"><thead><tr><th>Campaign / channel</th><th>Spend</th><th>Budget</th><th>Applications</th><th>Hires</th><th>Cost / application</th><th>Cost / hire</th><th>Financial ROI</th></tr></thead><tbody>
              {campaignROI?.campaign_channels.map((item) => <tr key={item.channel_id}><td><strong>{item.campaign_name}</strong><div className="muted-small">{item.source_label || item.channel_key} · {nice(item.campaign_status)}</div>{item.sample_warning && <div className="muted-small analytics-sample-warning">Small sample (&lt;5)</div>}</td><td>{item.spend_amount == null ? "—" : number(item.spend_amount, 2) + " " + (item.spend_currency || "")}</td><td>{item.budget_amount == null ? "—" : number(item.budget_amount, 2) + " " + (item.budget_currency || "")}</td><td>{number(item.applications)}</td><td>{number(item.hires)}</td><td>{item.cost_per_application == null ? "—" : number(item.cost_per_application, 2) + " " + (item.spend_currency || "")}</td><td>{item.cost_per_hire == null ? "—" : number(item.cost_per_hire, 2) + " " + (item.spend_currency || "")}</td><td><span className="muted-small">Revenue data needed</span></td></tr>)}
              {!campaignROI?.campaign_channels.length && <tr><td colSpan={8}>No campaign channels are configured for this organisation.</td></tr>}
            </tbody></table></div>
            {campaignROI?.limitations.length ? <details className="analytics-details"><summary>Campaign attribution and ROI limitations</summary><ul>{campaignROI.limitations.map((item) => <li key={item}>{item}</li>)}</ul></details> : null}
          </section>
          <p className="muted-small analytics-footer">AQERITH Analytics · Metric definitions version {kpis ? "1.0" : "—"} · Null means unavailable or an insufficient denominator, not zero.</p>
        </main>
      </div>
    </div>
  );
}
