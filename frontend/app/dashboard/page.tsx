"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, API_BASE } from "@/lib/api";
import { getSupabaseClient } from "@/lib/supabase";
import { getActiveOrganizationId } from "@/lib/organization";

type MetricSet = {
  open_jobs: number;
  active_candidates: number;
  interviews_today: number;
  placements_active: number;
  placements_this_month: number;
};
type Pipeline = Record<string, number>;
type Job = {
  id: string;
  title: string;
  client: string;
  status: string;
  applicants: number;
  days_open: number;
  health: "needs_attention" | "on_track";
  health_reasons: string[];
};
type Priority = {
  id: string;
  type: string;
  title: string;
  description: string;
  href: string;
  due_at: string | null;
};
type Activity = {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  metadata: Record<string, unknown> | null;
  created_at: string;
  actor_user_id: string | null;
  actor_name: string | null;
};
type DashboardData = {
  metrics: MetricSet;
  pipeline: Pipeline;
  jobs: Job[];
  vacancy_health: Array<{ id: string; title: string; applicants: number; days_open: number; reasons: string[] }>;
  priorities: Priority[];
  activity: Activity[];
  rules: { vacancy_target_days: number; vacancy_min_applications: number; offer_expiry_window_days: number; awaiting_decision_days: number };
  date_range: { from: string | null; to: string | null };
};

const stages = [
  { key: "new", label: "Applied" },
  { key: "screening", label: "Screening" },
  { key: "submitted", label: "Shortlisted / Submitted" },
  { key: "interview", label: "Interview" },
  { key: "offer", label: "Offer" },
  { key: "hired", label: "Hired" },
];
const terminalStages = [
  { key: "rejected", label: "Rejected" },
  { key: "withdrawn", label: "Withdrawn" },
];

function localDate(daysAgo = 0) {
  const date = new Date();
  date.setDate(date.getDate() - daysAgo);
  return [date.getFullYear(), String(date.getMonth() + 1).padStart(2, "0"), String(date.getDate()).padStart(2, "0")].join("-");
}

function formatDate(value: string | null | undefined) {
  if (!value) return "No due date";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date unavailable";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function friendlyAction(action: string) {
  return action.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export default function Dashboard() {
  const router = useRouter();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [dateFrom, setDateFrom] = useState(localDate(30));
  const [dateTo, setDateTo] = useState(localDate());
  const [search, setSearch] = useState("");
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);

  const loadDashboard = useCallback(async () => {
    const org = getActiveOrganizationId();
    if (!API_BASE || !org) {
      setError("Dashboard configuration is missing. Select an organisation and try again.");
      setData(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ organization_id: org });
      if (dateFrom) params.set("date_from", dateFrom);
      if (dateTo) params.set("date_to", dateTo);
      const response = await apiFetch(API_BASE + "/api/dashboard?" + params.toString());
      if (!response.ok) {
        if (response.status === 401) throw new Error("Your session has expired. Sign in again to load dashboard data.");
        if (response.status === 403) throw new Error("You don't have access to this organisation's dashboard.");
        if (response.status === 503) throw new Error("Dashboard data is temporarily unavailable. Please retry.");
        throw new Error("We couldn't load the dashboard (HTTP " + response.status + ").");
      }
      setData(await response.json());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load dashboard data.");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [dateFrom, dateTo]);

  useEffect(() => { void loadDashboard(); }, [loadDashboard]);

  const totalPipeline = useMemo(
    () => Object.values(data?.pipeline ?? {}).reduce((total, count) => total + count, 0),
    [data],
  );

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = search.trim();
    if (value) router.push("/candidates?search=" + encodeURIComponent(value));
    else router.push("/candidates");
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <Link href="/dashboard" className="brand">AQERITH</Link>
        <div className="nav-label">Workspace</div>
        {[
          ["Dashboard", "/dashboard", "⌂"],
          ["Jobs", "/jobs", "▣"],
          ["Candidates", "/candidates", "♙"],
          ["Submissions", "/submissions", "↗"],
          ["Interviews", "/interviews", "◷"],
          ["Clients", "/clients", "□"],
          ["Onboarding", "/onboarding", "✓"],
          ["Offers", "/offers", "＄"],
          ["Placements", "/placements", "◈"],
          ["Advanced Search", "/search", "⌕"],
          ["Talent Pools", "/talent-pools", "♧"],
          ["Candidate Imports", "/imports", "⇧"],
          ["Campaigns", "/campaigns", "◎"],
        ].map(([label, href, symbol]) => (
          <Link key={label} href={href} className={"nav-item" + (label === "Dashboard" ? " active" : "")}>
            <span aria-hidden="true">{symbol}</span><span>{label}</span>
          </Link>
        ))}
        <div className="nav-label">Administration</div>
        <div className="nav-item"><span aria-hidden="true">⚙</span><span>Settings</span></div>
        <div className="nav-item"><span aria-hidden="true">?</span><span>Help &amp; support</span></div>
      </aside>

      <main className="main">
        <header className="topbar">
          <form className="dashboard-search-form" onSubmit={submitSearch}>
            <input className="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search candidates..." aria-label="Search candidates" />
            <button className="btn" type="submit">Search</button>
          </form>
          <div className="profile">
            <Link href="#priorities" aria-label="Jump to dashboard notifications and priorities" className="dashboard-notification" title="Review today's priorities">♧</Link>
            <div className="dashboard-user-menu">
              <button className="dashboard-user-trigger" type="button" aria-haspopup="menu" aria-expanded={userMenuOpen} onClick={() => setUserMenuOpen((open) => !open)}>
                <span className="avatar">A</span><span className="profile-link">Account</span><span aria-hidden="true">⌄</span>
              </button>
              {userMenuOpen && <div className="dashboard-user-dropdown" role="menu">
                <div className="dashboard-user-menu-title">AQERITH account</div>
                <button role="menuitem" type="button" disabled={signingOut} onClick={async () => {
                  setSigningOut(true);
                  try {
                    await getSupabaseClient().auth.signOut();
                    window.location.href = "/login";
                  } finally {
                    setSigningOut(false);
                  }
                }}>{signingOut ? "Signing out…" : "Sign out"}</button>
              </div>}
            </div>
          </div>
        </header>

        <section className="content dashboard-content">
          <div className="header-row">
            <div>
              <div className="eyebrow">Recruitment operations</div>
              <h1>Dashboard</h1>
              <p className="subtitle">Current recruitment snapshot. Pipeline and recent activity follow the selected date range.</p>
            </div>
            <div className="actions dashboard-actions">
              <Link href="/jobs" className="btn">View vacancies</Link>
              <Link href="/jobs?create=1" className="btn primary">+ Create requisition</Link>
            </div>
          </div>

          <div className="dashboard-filters">
            <label>From <input type="date" value={dateFrom} max={dateTo || undefined} onChange={(event) => setDateFrom(event.target.value)} /></label>
            <label>To <input type="date" value={dateTo} min={dateFrom || undefined} onChange={(event) => setDateTo(event.target.value)} /></label>
            <button className="btn" onClick={() => { setDateFrom(localDate(30)); setDateTo(localDate()); }}>Last 30 days</button>
            <button className="btn" onClick={() => void loadDashboard()} disabled={loading}>{loading ? "Refreshing…" : "Refresh"}</button>
          </div>

          {error && (
            <div className="dashboard-error" role="alert">
              <div><strong>Dashboard couldn't be loaded</strong><p>{error}</p></div>
              <button className="btn" onClick={() => void loadDashboard()} disabled={loading}>Retry</button>
            </div>
          )}

          <div className="metrics dashboard-metrics">
            {[
              { title: "Open jobs", value: data?.metrics.open_jobs, icon: "▣", href: "/jobs?status=open", detail: "Currently open vacancies" },
              { title: "Active candidates", value: data?.metrics.active_candidates, icon: "♙", href: "/candidates", detail: "Accessible candidate records" },
              { title: "Interviews today", value: data?.metrics.interviews_today, icon: "◷", href: "/interviews", detail: "Scheduled for today" },
              { title: "Active placements", value: data?.metrics.placements_active, icon: "◈", href: "/placements", detail: (data?.metrics.placements_this_month ?? 0) + " created this month" },
            ].map((metric) => (
              <Link key={metric.title} href={metric.href} className="card dashboard-metric-card" aria-label={metric.title + ", view records"}>
                <div className="dashboard-metric-top"><span className="dashboard-metric-icon" aria-hidden="true">{metric.icon}</span><span className="metric-title">{metric.title}</span></div>
                <div className="metric-value">{loading ? <span className="dashboard-skeleton" /> : (metric.value ?? "—")}</div>
                <div className="metric-foot dashboard-metric-detail">{metric.detail}</div>
              </Link>
            ))}
          </div>

          <div className="dashboard-section-grid">
            <section className="card dashboard-priorities" id="priorities">
              <div className="card-head"><span className="card-title">Today's priorities</span><span className="badge blue">{data?.priorities.length ?? 0} items</span></div>
              {loading ? <div className="dashboard-loading-lines"><span /><span /><span /></div> : !data?.priorities.length ? (
                <div className="dashboard-empty"><strong>You're all caught up</strong><p>No outstanding priority items were found for the current data.</p></div>
              ) : (
                <div className="dashboard-priority-list">
                  {data.priorities.map((item) => (
                    <Link key={item.type + item.id} href={item.href} className="dashboard-priority-row">
                      <span className={"dashboard-priority-icon priority-" + item.type} aria-hidden="true">!</span>
                      <span className="dashboard-priority-copy"><strong>{item.title}</strong><span>{item.description}</span></span>
                      <span className="dashboard-priority-date">{formatDate(item.due_at)}</span>
                      <span aria-hidden="true">→</span>
                    </Link>
                  ))}
                </div>
              )}
            </section>

            <section className="card dashboard-quick-actions">
              <div className="card-head"><span className="card-title">Quick actions</span></div>
              <Link href="/jobs?create=1" className="dashboard-quick-action"><span aria-hidden="true">＋</span><span><strong>Create requisition</strong><small>Open vacancy management</small></span><span aria-hidden="true">→</span></Link>
              <Link href="/candidates?create=1" className="dashboard-quick-action"><span aria-hidden="true">♙</span><span><strong>Add candidate</strong><small>Create a candidate profile or import a CV</small></span><span aria-hidden="true">→</span></Link>
              <Link href="/match-lab" className="dashboard-quick-action"><span aria-hidden="true">⌕</span><span><strong>Find matches</strong><small>Choose a vacancy to begin candidate matching</small></span><span aria-hidden="true">→</span></Link>
              <Link href="/interviews?create=1" className="dashboard-quick-action"><span aria-hidden="true">◷</span><span><strong>Schedule interview</strong><small>Start interview scheduling</small></span><span aria-hidden="true">→</span></Link>
            </section>
          </div>

          <section className="card dashboard-pipeline-section">
            <div className="card-head"><div><span className="card-title">Hiring pipeline</span><p className="muted-small">Application counts for the selected date range · {totalPipeline} total</p></div><Link href="/submissions" className="link">View submissions →</Link></div>
            <div className="pipeline dashboard-pipeline">
              {stages.map((stage) => (
                <Link key={stage.key} href={"/submissions?status=" + stage.key} className="stage dashboard-stage">
                  <strong>{loading ? "—" : (data?.pipeline[stage.key] ?? 0)}</strong><span>{stage.label}</span>
                </Link>
              ))}
            </div>
            <div className="dashboard-terminal-stages">
              <span className="muted-small">Terminal outcomes</span>
              {terminalStages.map((stage) => (
                <Link key={stage.key} href={"/submissions?status=" + stage.key} className="dashboard-terminal-link">
                  {stage.label} <strong>{loading ? "—" : (data?.pipeline[stage.key] ?? 0)}</strong>
                </Link>
              ))}
            </div>
          </section>

          <div className="dashboard-section-grid dashboard-lower-grid">
            <section className="card">
              <div className="card-head"><span className="card-title">Vacancy health</span><Link href="/jobs" className="link">All vacancies →</Link></div>
              <p className="muted-small">Rules: flag open roles older than {data?.rules.vacancy_target_days ?? 30} days or with fewer than {data?.rules.vacancy_min_applications ?? 3} applications.</p>
              {loading ? <div className="dashboard-loading-lines"><span /><span /><span /></div> : !data?.jobs.length ? (
                <div className="dashboard-empty"><strong>No vacancies to display</strong><p>Create a requisition to start tracking vacancy health.</p><Link href="/jobs" className="btn">View jobs</Link></div>
              ) : (
                <div className="dashboard-vacancy-list">
                  {data.jobs.map((job) => (
                    <Link key={job.id} href={"/jobs?job_id=" + job.id} className="dashboard-vacancy-row">
                      <span className="dashboard-vacancy-copy"><strong>{job.title}</strong><small>{job.client} · {job.days_open} days open · {job.applicants} applications</small>
                      {job.health_reasons.length > 0 && <small className="dashboard-health-reasons">{job.health_reasons.join(" · ")}</small>}</span>
                      <span className={"badge " + (job.health === "needs_attention" ? "amber" : "green")}>{job.health === "needs_attention" ? "Needs attention" : "On track"}</span>
                    </Link>
                  ))}
                </div>
              )}
            </section>

            <section className="card">
              <div className="card-head"><span className="card-title">Recent activity</span><span className="muted-small">Latest recorded events</span></div>
              {loading ? <div className="dashboard-loading-lines"><span /><span /><span /></div> : !data?.activity.length ? (
                <div className="dashboard-empty"><strong>No activity yet</strong><p>Recruitment events will appear here when recorded.</p></div>
              ) : (
                <div className="activity dashboard-activity">
                  {data.activity.map((item) => {
                    const target = ["job", "jobs"].includes(item.entity_type) ? "/jobs?job_id=" + item.entity_id : ["candidate", "candidates"].includes(item.entity_type) ? "/candidates/" + item.entity_id : ["interview", "interviews"].includes(item.entity_type) ? "/interviews/" + item.entity_id : ["placement", "placements"].includes(item.entity_type) ? "/placements/" + item.entity_id : ["offer", "offers"].includes(item.entity_type) ? "/offers/" + item.entity_id : "/submissions/" + item.entity_id;
                    return <Link key={item.id} href={target} className="activity-row dashboard-activity-row"><div className="dot" /><div className="activity-text"><strong>{friendlyAction(item.action)}</strong><div>{item.entity_type ? friendlyAction(item.entity_type) : "Recruitment event"} · {item.entity_id ? item.entity_id.slice(0, 8) : "Record"}</div><div className="activity-time">{formatDate(item.created_at)}{item.actor_name ? " · " + item.actor_name : ""}</div></div></Link>;
                  })}
                </div>
              )}
            </section>
          </div>
        </section>
      </main>
    </div>
  );
}
