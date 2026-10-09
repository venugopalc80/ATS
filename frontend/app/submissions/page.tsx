"use client";

import Link from "next/link";
import { DragEvent, useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";
const DEFAULT_ORGANIZATION_ID = process.env.NEXT_PUBLIC_ORGANIZATION_ID ?? "";

type Job = { id: string; title: string; status: string };
type Candidate = { id: string; first_name: string; last_name?: string | null; current_title?: string | null };
type ApplicationStatus = "new" | "screening" | "submitted" | "interview" | "offer" | "hired" | "rejected" | "withdrawn";
type Application = {
  id: string;
  job_id: string;
  candidate_id: string;
  status: ApplicationStatus;
  match_score?: number | null;
  human_reviewed: boolean;
  created_at: string;
};

const statuses: ApplicationStatus[] = ["new", "screening", "submitted", "interview", "offer", "hired", "rejected", "withdrawn"];
const boardStatuses: ApplicationStatus[] = ["new", "screening", "submitted", "interview", "offer", "hired"];

const allowedTransitions: Record<ApplicationStatus, ApplicationStatus[]> = {
  new: ["screening", "rejected", "withdrawn"],
  screening: ["submitted", "rejected", "withdrawn"],
  submitted: ["interview", "rejected", "withdrawn"],
  interview: ["offer", "rejected", "withdrawn"],
  offer: ["hired", "rejected", "withdrawn"],
  hired: [],
  rejected: [],
  withdrawn: [],
};

function candidateName(candidate?: Candidate) {
  return candidate ? [candidate.first_name, candidate.last_name].filter(Boolean).join(" ") : "Unknown candidate";
}

export default function SubmissionsPage() {
  const [applications, setApplications] = useState<Application[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [status, setStatus] = useState<"all" | ApplicationStatus>("all");
  const [query, setQuery] = useState("");
  const [viewMode, setViewMode] = useState<"table" | "board">("table");
  const [sortBy, setSortBy] = useState<"candidate" | "job" | "source" | "status" | "created">("created");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);
  const pageSize = 25;
  const [savedViews, setSavedViews] = useState<Array<{ name: string; query: string; status: string }>>([]);
  const [activeView, setActiveView] = useState("All applicants");
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [selectedJob, setSelectedJob] = useState("");
  const [selectedCandidate, setSelectedCandidate] = useState("");
  const [source, setSource] = useState("Direct");
  const [saving, setSaving] = useState(false);

  const jobMap = useMemo(() => new Map(jobs.map((job) => [job.id, job])), [jobs]);
  const candidateMap = useMemo(() => new Map(candidates.map((candidate) => [candidate.id, candidate])), [candidates]);

  useEffect(() => {
    try { const stored = window.localStorage.getItem("talentos_applicant_views"); if (stored) setSavedViews(JSON.parse(stored)); } catch { /* Ignore invalid saved views. */ }
  }, []);

  useEffect(() => {
    async function load() {
      const organizationId = typeof window !== "undefined" ? window.localStorage.getItem("talentos_active_org") || DEFAULT_ORGANIZATION_ID : DEFAULT_ORGANIZATION_ID;
      if (!API_BASE || !organizationId) {
        setMessage("API configuration is missing.");
        setLoading(false);
        return;
      }
      try {
        const org = encodeURIComponent(organizationId);
        const [apps, jobResponse, candidateResponse] = await Promise.all([
          apiFetch(API_BASE + "/api/applications?organization_id=" + org),
          apiFetch(API_BASE + "/api/jobs?organization_id=" + org),
          apiFetch(API_BASE + "/api/candidates?organization_id=" + org),
        ]);
        if (!apps.ok || !jobResponse.ok || !candidateResponse.ok) throw new Error("Unable to load recruitment pipeline.");
        setApplications(await apps.json());
        setJobs(await jobResponse.json());
        setCandidates(await candidateResponse.json());
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Unable to load submissions.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const filtered = useMemo(() => applications.filter((application) => {
    const candidate = candidateMap.get(application.candidate_id);
    const job = jobMap.get(application.job_id);
    const haystack = [application.id, candidateName(candidate), candidate?.email, candidate?.phone, candidate?.city, candidate?.region, application.source, job?.title, application.status].filter(Boolean).join(" ").toLowerCase();
    return (status === "all" || application.status === status) && haystack.includes(query.toLowerCase());
  }).sort((a, b) => {
    const candidateA = candidateMap.get(a.candidate_id); const candidateB = candidateMap.get(b.candidate_id);
    const jobA = jobMap.get(a.job_id); const jobB = jobMap.get(b.job_id);
    let comparison = 0;
    if (sortBy === "candidate") comparison = candidateName(candidateA).localeCompare(candidateName(candidateB));
    else if (sortBy === "job") comparison = (jobA?.title ?? "").localeCompare(jobB?.title ?? "");
    else if (sortBy === "source") comparison = (a.source ?? "").localeCompare(b.source ?? "");
    else if (sortBy === "status") comparison = a.status.localeCompare(b.status);
    else comparison = a.created_at.localeCompare(b.created_at);
    return sortDirection === "asc" ? comparison : -comparison;
  }), [applications, candidateMap, jobMap, status, query, sortBy, sortDirection]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const pageApplications = filtered.slice((page - 1) * pageSize, page * pageSize);
  function changeSort(field: typeof sortBy) { if (sortBy === field) setSortDirection((direction) => direction === "asc" ? "desc" : "asc"); else { setSortBy(field); setSortDirection(field === "created" ? "desc" : "asc"); } }
  function saveView() {
    const name = window.prompt("Name this applicant view"); if (!name?.trim()) return;
    const next = [...savedViews.filter((view) => view.name.toLowerCase() !== name.trim().toLowerCase()), { name: name.trim(), query, status }];
    setSavedViews(next); setActiveView(name.trim()); window.localStorage.setItem("talentos_applicant_views", JSON.stringify(next)); setMessage("Applicant view saved.");
  }
  function applyView(name: string) {
    setActiveView(name);
    if (name === "All applicants") { setQuery(""); setStatus("all"); }
    else { const view = savedViews.find((item) => item.name === name); if (view) { setQuery(view.query); setStatus(view.status as "all" | ApplicationStatus); } }
    setPage(1);
  }

  async function changeStatus(application: Application, nextStatus: ApplicationStatus) {
    if (application.status === nextStatus) return;
    if (!allowedTransitions[application.status].includes(nextStatus)) {
      setMessage("That stage transition is not allowed.");
      return;
    }
    try {
      const response = await apiFetch(API_BASE + "/api/applications/" + application.id, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: nextStatus }),
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(detail?.detail ?? "Unable to update application.");
      }
      const updated: Application = await response.json();
      setApplications((current) => current.map((item) => item.id === updated.id ? updated : item));
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to update application.");
    }
  }

  function onDragStart(event: DragEvent<HTMLDivElement>, applicationId: string) {
    event.dataTransfer.setData("text/application-id", applicationId);
  }

  function onDrop(event: DragEvent<HTMLDivElement>, nextStatus: ApplicationStatus) {
    event.preventDefault();
    const id = event.dataTransfer.getData("text/application-id");
    const application = applications.find((item) => item.id === id);
    if (application) void changeStatus(application, nextStatus);
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <Link href="/" className="brand">Talent<span>OS</span></Link>
        <div className="nav-label">Workspace</div>
        <Link href="/" className="nav-item"><span>⌂</span><span>Dashboard</span></Link>
        <Link href="/jobs" className="nav-item"><span>▣</span><span>Jobs</span></Link>
        <Link href="/candidates" className="nav-item"><span>●</span><span>Candidates</span></Link>
        <div className="nav-item active"><span>↗</span><span>Submissions</span></div>
        <Link href="/interviews" className="nav-item"><span>◷</span><span>Interviews</span></Link>
        <div className="nav-item"><span>□</span><span>Clients</span></div>
        <div className="nav-item"><span>◇</span><span>Vendors</span></div>
        <div className="nav-item"><span>♧</span><span>Talent Bench</span></div>
        <div className="nav-item"><span>✓</span><span>Onboarding</span></div>
        <Link href="/placements" className="nav-item"><span>◈</span><span>Placements</span></Link>
        <div className="nav-item"><span>◌</span><span>Leads</span></div>
        <div className="nav-item"><span>▤</span><span>Reports</span></div>
        <div className="nav-label">Administration</div>
        <div className="nav-item"><span>⚙</span><span>Settings</span></div>
      </aside>

      <main className="main">
        <header className="topbar">
          <input className="search" placeholder="Search applicants, email, job, source..." aria-label="Search applicants" value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} />
          <div className="profile"><span>Acme Recruitment</span><div className="avatar">VG</div></div>
        </header>

        <section className="content">
          <div className="header-row">
            <div>
              <div className="eyebrow">Recruitment pipeline</div>
              <h1>Applicants</h1>
              <p className="subtitle">A unified applicant register and recruitment pipeline.</p>
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}><button className={"btn " + (viewMode === "table" ? "primary" : "")} onClick={() => setViewMode("table")}>Applicant register</button><button className={"btn " + (viewMode === "board" ? "primary" : "")} onClick={() => setViewMode("board")}>Pipeline board</button><button className="btn primary" onClick={() => { setMessage(""); setShowCreate(true); }}>+ New applicant</button></div>
          </div>

          <div className="card" style={{ marginBottom: 16 }}><div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}><select className="filter" aria-label="Saved applicant views" value={activeView} onChange={(event) => applyView(event.target.value)}><option>All applicants</option>{savedViews.map((view) => <option key={view.name}>{view.name}</option>)}</select><button className="btn" onClick={saveView}>+ Add view</button><select className="filter" aria-label="Filter applicant status" value={status} onChange={(event) => { setStatus(event.target.value as "all" | ApplicationStatus); setPage(1); }}><option value="all">All statuses</option>{statuses.map((item) => <option key={item} value={item}>{item.replaceAll("_", " ")}</option>)}</select><span className="muted-small">{filtered.length} applicant{filtered.length === 1 ? "" : "s"}</span></div></div>
          {message && <div className="notice">{message}</div>}

          {showCreate && (
            <div className="modal-backdrop">
              <form className="modal" onSubmit={async (event) => {
                event.preventDefault();
                if (!selectedJob || !selectedCandidate) { setMessage("Select both a job and candidate."); return; }
                setSaving(true);
                try {
                  const organizationId = localStorage.getItem("talentos_active_org") || DEFAULT_ORGANIZATION_ID;
                  const response = await apiFetch(API_BASE + "/api/applications", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ organization_id: organizationId, job_id: selectedJob, candidate_id: selectedCandidate, source, status: "new" }),
                  });
                  if (!response.ok) {
                    const detail = await response.json().catch(() => null);
                    throw new Error(detail?.detail ?? "Unable to create submission.");
                  }
                  const created: Application = await response.json();
                  setApplications((current) => [created, ...current]);
                  setShowCreate(false);
                  setSelectedJob("");
                  setSelectedCandidate("");
                  setSource("Direct");
                  setMessage("Submission created successfully.");
                } catch (error) {
                  setMessage(error instanceof Error ? error.message : "Unable to create submission.");
                } finally {
                  setSaving(false);
                }
              }}>
                <div className="card-head">
                  <span className="card-title">New submission</span>
                  <button type="button" className="icon-button" onClick={() => setShowCreate(false)}>×</button>
                </div>
                <label>Candidate
                  <select required value={selectedCandidate} onChange={(event) => setSelectedCandidate(event.target.value)}>
                    <option value="">Select candidate</option>
                    {candidates.map((candidate) => <option key={candidate.id} value={candidate.id}>{candidateName(candidate)}</option>)}
                  </select>
                </label>
                <label>Job
                  <select required value={selectedJob} onChange={(event) => setSelectedJob(event.target.value)}>
                    <option value="">Select job</option>
                    {jobs.filter((job) => job.status === "open" || job.status === "on_hold").map((job) => <option key={job.id} value={job.id}>{job.title}</option>)}
                  </select>
                </label>
                <label>Source
                  <input value={source} onChange={(event) => setSource(event.target.value)} placeholder="Direct, LinkedIn, referral..." />
                </label>
                <div className="modal-actions">
                  <button type="button" className="btn" onClick={() => setShowCreate(false)}>Cancel</button>
                  <button className="btn primary" disabled={saving}>{saving ? "Creating..." : "Create submission"}</button>
                </div>
              </form>
            </div>
          )}

          {viewMode === "board" && <div className="pipeline-board">
            {boardStatuses.map((stage) => {
              const stageApps = filtered.filter((application) => application.status === stage);
              return (
                <div key={stage} className="pipeline-column" onDragOver={(event) => event.preventDefault()} onDrop={(event) => onDrop(event, stage)}>
                  <div className="pipeline-column-head">
                    <span>{stage.replaceAll("_", " ")}</span>
                    <span className="muted-small">{stageApps.length}</span>
                  </div>
                  <div className="pipeline-cards">
                    {stageApps.map((application) => {
                      const candidate = candidateMap.get(application.candidate_id);
                      const job = jobMap.get(application.job_id);
                      return (
                        <div key={application.id} className="pipeline-card" draggable onDragStart={(event) => onDragStart(event, application.id)}>
                          <Link className="link" href={"/submissions/" + application.id}><strong>{candidateName(candidate)}</strong></Link>
                          <div className="muted-small">{job?.title ?? "Unknown job"}</div>
                          {application.match_score != null && <span className="badge green">{application.match_score}% match</span>}
                          <select
                            className="filter"
                            value={application.status}
                            onChange={(event) => void changeStatus(application, event.target.value as ApplicationStatus)}
                          >
                            <option value={application.status}>{application.status.replaceAll("_", " ")}</option>
                            {allowedTransitions[application.status].map((next) => (
                              <option key={next} value={next}>{next.replaceAll("_", " ")}</option>
                            ))}
                          </select>
                        </div>
                      );
                    })}
                    {!stageApps.length && <div className="pipeline-empty">Drop candidates here</div>}
                  </div>
                </div>
              );
            })}
          </div>}

          {viewMode === "table" && <div className="card">
            <div className="card-head"><span className="card-title">Applicant register</span><span className="muted-small">{loading ? "Loading..." : "Live data · " + filtered.length + " records"}</span></div>
            <div style={{ overflowX: "auto" }}><table className="table applicant-table">
              <thead><tr><th>Applicant ID</th><th><button className="table-sort" onClick={() => changeSort("candidate")}>Applicant name {sortBy === "candidate" ? (sortDirection === "asc" ? "↑" : "↓") : ""}</button></th><th>Email address</th><th>Mobile number</th><th>City / region</th><th><button className="table-sort" onClick={() => changeSort("source")}>Source {sortBy === "source" ? (sortDirection === "asc" ? "↑" : "↓") : ""}</button></th><th><button className="table-sort" onClick={() => changeSort("status")}>Applicant status {sortBy === "status" ? (sortDirection === "asc" ? "↑" : "↓") : ""}</button></th><th><button className="table-sort" onClick={() => changeSort("job")}>Job title {sortBy === "job" ? (sortDirection === "asc" ? "↑" : "↓") : ""}</button></th><th>Match / review</th><th><button className="table-sort" onClick={() => changeSort("created")}>Applied {sortBy === "created" ? (sortDirection === "asc" ? "↑" : "↓") : ""}</button></th></tr></thead>
              <tbody>
                {loading ? <tr><td colSpan={10}>Loading applicants...</td></tr> : filtered.length === 0 ? <tr><td colSpan={10}>No applicants match these filters. Create a new application or adjust your search.</td></tr> : pageApplications.map((application) => {
                    const candidate = candidateMap.get(application.candidate_id);
                    const job = jobMap.get(application.job_id);
                    return (
                      <tr key={application.id}>
                        <td><Link className="link" href={"/submissions/" + application.id}>{application.id.slice(0, 8).toUpperCase()}</Link></td>
                        <td><Link className="link" href={"/submissions/" + application.id}><strong>{candidateName(candidate)}</strong></Link></td>
                        <td>{candidate?.email ?? "—"}</td><td>{candidate?.phone ?? "—"}</td><td>{[candidate?.city, candidate?.region].filter(Boolean).join(", ") || "—"}</td><td>{application.source || "Direct"}</td>
                        <td><select className="filter" aria-label={"Status for " + candidateName(candidate)} value={application.status} onChange={(event) => void changeStatus(application, event.target.value as ApplicationStatus)}><option value={application.status}>{application.status.replaceAll("_", " ")}</option>{allowedTransitions[application.status].map((next) => <option key={next} value={next}>{next.replaceAll("_", " ")}</option>)}</select></td>
                        <td>{job?.title ?? "Unknown job"}</td><td>{application.match_score != null ? <span className="badge green">{application.match_score}% match</span> : <span className={"badge " + (application.human_reviewed ? "green" : "amber")}>{application.human_reviewed ? "Reviewed" : "Needs review"}</span>}</td><td>{new Date(application.created_at).toLocaleDateString()}</td>
                      </tr>
                    );
                  })}
              </tbody>
            </table></div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap", paddingTop: 14 }}><span className="muted-small">Showing {filtered.length ? (page - 1) * pageSize + 1 : 0}–{Math.min(page * pageSize, filtered.length)} of {filtered.length}</span><div style={{ display: "flex", gap: 8, alignItems: "center" }}><button className="btn" disabled={page <= 1} onClick={() => setPage((current) => Math.max(1, current - 1))}>Previous</button><span className="muted-small">Page {page} of {pageCount}</span><button className="btn" disabled={page >= pageCount} onClick={() => setPage((current) => Math.min(pageCount, current + 1))}>Next</button></div></div>
          </div>}
        </section>
      </main>
    </div>
  );
}
