"use client";

import Link from "next/link";
import { DragEvent, FormEvent, useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api";
import { getActiveOrganizationId } from "@/lib/organization";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";
const DEFAULT_ORGANIZATION_ID = process.env.NEXT_PUBLIC_ORGANIZATION_ID ?? "";

type Job = { id: string; title: string; status: string };
type Candidate = { id: string; first_name: string; last_name?: string | null; email?: string | null; phone?: string | null; city?: string | null; region?: string | null; current_title?: string | null };
type ApplicationStatus = "new" | "screening" | "shortlisted" | "submitted" | "interview" | "assessment" | "offer" | "hired" | "rejected" | "withdrawn";
type Application = {
  id: string;
  job_id: string;
  candidate_id: string;
  status: ApplicationStatus;
  source?: string | null;
  match_score?: number | null;
  human_reviewed: boolean;
  created_at: string;
};

type Recruiter = { id: string; full_name?: string | null; email?: string | null };
type ApplicationAssignment = { application_id: string; recruiter_id: string | null; assigned_at: string | null };
type ApplicationSLAPolicy = {
  organization_id: string;
  initial_review_minutes: number;
  first_recruiter_action_minutes: number;
  candidate_follow_up_minutes: number;
  post_interview_update_minutes: number;
  timezone: string;
  business_days_only: boolean;
  business_hours_start: string;
  business_hours_end: string;
  working_days: number[];
  enabled: boolean;
};
const DEFAULT_SLA_POLICY = {
  initial_review_minutes: 1440,
  first_recruiter_action_minutes: 2880,
  candidate_follow_up_minutes: 2880,
  post_interview_update_minutes: 1440,
  timezone: "UTC",
  business_days_only: true,
  business_hours_start: "09:00",
  business_hours_end: "17:00",
  working_days: [1, 2, 3, 4, 5],
  enabled: true,
};

type ApplicationStageConfig = {
  organization_id: string;
  stage_key: ApplicationStatus;
  label: string;
  display_order: number;
  allowed_next_stages: ApplicationStatus[];
  is_terminal: boolean;
  enabled: boolean;
};

function candidateName(candidate?: Candidate) {
  return candidate ? [candidate.first_name, candidate.last_name].filter(Boolean).join(" ") : "Unknown candidate";
}

export default function SubmissionsPage() {
  const [applications, setApplications] = useState<Application[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [stages, setStages] = useState<ApplicationStageConfig[]>([]);
  const [recruiters, setRecruiters] = useState<Recruiter[]>([]);
  const [assignments, setAssignments] = useState<Record<string, string | null>>({});
  const [canManageAssignments, setCanManageAssignments] = useState(false);
  const [savingAssignmentId, setSavingAssignmentId] = useState<string | null>(null);
  const [slaPolicy, setSlaPolicy] = useState<ApplicationSLAPolicy | null>(null);\n  const [savingSlaPolicy, setSavingSlaPolicy] = useState(false);
  const [status, setStatus] = useState<"all" | ApplicationStatus>("all");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [viewMode, setViewMode] = useState<"table" | "board">("table");
  const [sortBy, setSortBy] = useState<"candidate" | "job" | "source" | "status" | "created">("created");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);
  const pageSize = 25;
  const [savedViews, setSavedViews] = useState<Array<{ name: string; query: string; status: string; sourceFilter?: string }>>([]);
  const [activeView, setActiveView] = useState("All applicants");
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [selectedJob, setSelectedJob] = useState("");
  const [selectedCandidate, setSelectedCandidate] = useState("");
  const [source, setSource] = useState("Direct");
  const [saving, setSaving] = useState(false);
  const [selectedApplicationIds, setSelectedApplicationIds] = useState<string[]>([]);
  const [bulkStatus, setBulkStatus] = useState<ApplicationStatus | "">("");
  const [bulkSaving, setBulkSaving] = useState(false);

  const jobMap = useMemo(() => new Map(jobs.map((job) => [job.id, job])), [jobs]);
  const candidateMap = useMemo(() => new Map(candidates.map((candidate) => [candidate.id, candidate])), [candidates]);
  const stageMap = useMemo(() => new Map(stages.map((stage) => [stage.stage_key, stage])), [stages]);
  const stageLabel = (value: ApplicationStatus) => stageMap.get(value)?.label ?? value.replaceAll("_", " ");

  useEffect(() => {
    const requestedStatus = new URLSearchParams(window.location.search).get("status");
    if (requestedStatus && ["new", "screening", "shortlisted", "submitted", "interview", "assessment", "offer", "hired", "rejected", "withdrawn"].includes(requestedStatus)) {
      setStatus(requestedStatus as ApplicationStatus);
    }
  }, []);

  useEffect(() => {
    try { const stored = window.localStorage.getItem("talentos_applicant_views"); if (stored) setSavedViews(JSON.parse(stored)); } catch { /* Ignore invalid saved views. */ }
  }, []);

  useEffect(() => {
    async function load() {
      const organizationId = getActiveOrganizationId(DEFAULT_ORGANIZATION_ID);
      if (!API_BASE || !organizationId) {
        setMessage("API configuration is missing.");
        setLoading(false);
        return;
      }
      try {
        const org = encodeURIComponent(organizationId);
        const [apps, jobResponse, candidateResponse, stageResponse, recruiterResponse, assignmentResponse, meResponse] = await Promise.all([
          apiFetch(API_BASE + "/api/applications?organization_id=" + org),
          apiFetch(API_BASE + "/api/jobs?organization_id=" + org),
          apiFetch(API_BASE + "/api/candidates?organization_id=" + org),
          apiFetch(API_BASE + "/api/applications/stages?organization_id=" + org),
          apiFetch(API_BASE + "/api/applications/recruiters?organization_id=" + org),
          apiFetch(API_BASE + "/api/applications/assignments?organization_id=" + org),
          apiFetch(API_BASE + "/api/me"),
        ]);
        if (!apps.ok || !jobResponse.ok || !candidateResponse.ok || !stageResponse.ok || !recruiterResponse.ok || !assignmentResponse.ok || !meResponse.ok) throw new Error("Unable to load recruitment pipeline, recruiter directory and assignment data.");
        setApplications(await apps.json());
        setJobs(await jobResponse.json());
        setCandidates(await candidateResponse.json());
        setStages(await stageResponse.json());
        setRecruiters(await recruiterResponse.json());
        const assignmentRows: ApplicationAssignment[] = await assignmentResponse.json();
        setAssignments(Object.fromEntries(assignmentRows.map((item) => [item.application_id, item.recruiter_id])));
        const me = await meResponse.json();
        const membership = (me.organizations ?? []).find((item: { id: string; role: string }) => item.id === organizationId);
        setCanManageAssignments(membership?.role === "owner" || membership?.role === "admin");
        setSlaPolicy({ organization_id: organizationId, ...DEFAULT_SLA_POLICY });
        const slaResponse = await apiFetch(API_BASE + "/api/applications/sla-policy?organization_id=" + org);
        if (slaResponse.ok) setSlaPolicy(await slaResponse.json());
        else if (slaResponse.status !== 404) throw new Error("Unable to load the organisation SLA policy.");
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
    const normalizedSource = (application.source || "Direct").trim();
    return (status === "all" || application.status === status)
      && (sourceFilter === "all" || normalizedSource.toLowerCase() === sourceFilter.toLowerCase())
      && haystack.includes(query.toLowerCase());
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
  }), [applications, candidateMap, jobMap, status, sourceFilter, query, sortBy, sortDirection]);

  const sourceOptions = useMemo(() => Array.from(new Set(applications.map((application) => (application.source || "Direct").trim()).filter(Boolean))).sort((a, b) => a.localeCompare(b)), [applications]);
  const newCount = applications.filter((application) => application.status === "new").length;
  const screeningCount = applications.filter((application) => application.status === "screening").length;
  const interviewCount = applications.filter((application) => application.status === "interview").length;

  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const pageApplications = filtered.slice((page - 1) * pageSize, page * pageSize);
  function changeSort(field: typeof sortBy) { if (sortBy === field) setSortDirection((direction) => direction === "asc" ? "desc" : "asc"); else { setSortBy(field); setSortDirection(field === "created" ? "desc" : "asc"); } }
  function saveView() {
    const name = window.prompt("Name this applicant view"); if (!name?.trim()) return;
    const next = [...savedViews.filter((view) => view.name.toLowerCase() !== name.trim().toLowerCase()), { name: name.trim(), query, status, sourceFilter }];
    setSavedViews(next); setActiveView(name.trim()); window.localStorage.setItem("talentos_applicant_views", JSON.stringify(next)); setMessage("Applicant view saved.");
  }
  function applyView(name: string) {
    setActiveView(name);
    if (name === "All applicants") { setQuery(""); setStatus("all"); setSourceFilter("all"); }
    else { const view = savedViews.find((item) => item.name === name); if (view) { setQuery(view.query); setStatus(view.status as "all" | ApplicationStatus); setSourceFilter(view.sourceFilter ?? "all"); } }
    setPage(1);
  }

  async function changeStatus(application: Application, nextStatus: ApplicationStatus) {
    if (application.status === nextStatus) return;
    const currentStage = stageMap.get(application.status);
    const targetStage = stageMap.get(nextStatus);
    if (!currentStage?.allowed_next_stages.includes(nextStatus) || !targetStage?.enabled) {
      setMessage("That stage transition is not allowed by this organisation's workflow.");
      return;
    }
    const reason = window.prompt("Why is this application moving to " + targetStage.label + "?");
    if (reason === null) return;
    const normalizedReason = reason.trim();
    if (!normalizedReason || normalizedReason.length > 1000) {
      setMessage("Enter a reason between 1 and 1000 characters to record this stage change.");
      return;
    }
    try {
      const response = await apiFetch(API_BASE + "/api/applications/" + application.id + "/transition", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: nextStatus, reason: normalizedReason }),
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

  async function saveSlaPolicy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!slaPolicy || savingSlaPolicy) return;
    setSavingSlaPolicy(true);
    try {
      const response = await apiFetch(API_BASE + "/api/applications/sla-policy", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(slaPolicy),
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(detail?.detail ?? "Unable to save SLA policy.");
      }
      setSlaPolicy(await response.json());
      setMessage("Recruitment SLA policy saved.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to save SLA policy.");
    } finally {
      setSavingSlaPolicy(false);
    }
  }

  async function changeAssignment(application: Application, recruiterId: string) {
    const currentRecruiterId = assignments[application.id] ?? null;
    const nextRecruiterId = recruiterId || null;
    if (currentRecruiterId === nextRecruiterId || savingAssignmentId) return;
    const reason = window.prompt(nextRecruiterId ? "Why is this application being assigned or reassigned?" : "Why is this application being unassigned?");
    if (reason === null) return;
    if (!reason.trim() || reason.trim().length > 1000) {
      setMessage("Enter an assignment reason between 1 and 1000 characters.");
      return;
    }
    setSavingAssignmentId(application.id);
    try {
      const response = await apiFetch(API_BASE + "/api/applications/" + application.id + "/assignment", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ recruiter_id: nextRecruiterId, reason: reason.trim() }),
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(detail?.detail ?? "Unable to update recruiter assignment.");
      }
      const updated: ApplicationAssignment = await response.json();
      setAssignments((current) => ({ ...current, [application.id]: updated.recruiter_id }));
      setMessage(nextRecruiterId ? "Recruiter assignment updated." : "Application unassigned.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to update recruiter assignment.");
    } finally {
      setSavingAssignmentId(null);
    }
  }

  async function runBulkTransition() {
    if (!selectedApplicationIds.length || !bulkStatus || bulkSaving) return;
    const reason = window.prompt("Why are these applications moving to " + stageLabel(bulkStatus) + "?");
    if (reason === null) return;
    const normalizedReason = reason.trim();
    if (!normalizedReason || normalizedReason.length > 1000) {
      setMessage("Enter a reason between 1 and 1000 characters to record this bulk stage change.");
      return;
    }
    setBulkSaving(true);
    try {
      const response = await apiFetch(API_BASE + "/api/applications/bulk-transition", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          application_ids: selectedApplicationIds,
          status: bulkStatus,
          reason: normalizedReason,
        }),
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(detail?.detail ?? "Unable to update selected applications.");
      }
      const result: {
        requested: number;
        succeeded: number;
        failed: number;
        results: Array<{ application_id: string; success: boolean; status?: ApplicationStatus | null; error?: string | null }>;
      } = await response.json();
      const successful = new Map(
        result.results.filter((item) => item.success && item.status).map((item) => [item.application_id, item.status as ApplicationStatus]),
      );
      setApplications((current) => current.map((item) => {
        const nextStatus = successful.get(item.id);
        return nextStatus ? { ...item, status: nextStatus } : item;
      }));
      setSelectedApplicationIds(result.results.filter((item) => !item.success).map((item) => item.application_id));
      setMessage(
        result.failed
          ? result.succeeded + " application(s) moved; " + result.failed + " failed. Failed records remain selected so you can review them."
          : result.succeeded + " application(s) moved successfully.",
      );
      setBulkStatus("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to update selected applications.");
    } finally {
      setBulkSaving(false);
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
        <Link href="/dashboard" className="brand">AQERITH</Link>
        <div className="nav-label">Workspace</div>
        <Link href="/dashboard" className="nav-item"><span>⌂</span><span>Dashboard</span></Link>
        <Link href="/jobs" className="nav-item"><span>▣</span><span>Jobs</span></Link>
        <Link href="/candidates" className="nav-item"><span>●</span><span>Candidates</span></Link>
        <div className="nav-item active"><span>↗</span><span>Applications Inbox</span></div>
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
              <div className="eyebrow">Recruitment operations</div>
              <h1>Recruiter Applications Inbox</h1>
              <p className="subtitle">Review incoming applications, identify their source and move each candidate through the hiring process.</p>
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}><button className={"btn " + (viewMode === "table" ? "primary" : "")} onClick={() => setViewMode("table")}>Inbox list</button><button className={"btn " + (viewMode === "board" ? "primary" : "")} onClick={() => setViewMode("board")}>Pipeline board</button><button className="btn primary" onClick={() => { setMessage(""); setShowCreate(true); }}>+ Create application</button></div>
          </div>

          <div className="metrics" style={{ marginTop: 8 }}>
            <button className="card" style={{ textAlign: "left", borderColor: status === "new" ? "var(--primary)" : "var(--line)" }} onClick={() => { setStatus(status === "new" ? "all" : "new"); setPage(1); }}><div className="metric-title">New applications</div><div className="metric-value">{newCount}</div><div className="metric-foot">Needs initial review</div></button>
            <div className="card"><div className="metric-title">In screening</div><div className="metric-value">{screeningCount}</div><div className="metric-foot">Active review</div></div>
            <div className="card"><div className="metric-title">Interviews</div><div className="metric-value">{interviewCount}</div><div className="metric-foot">Interview stage</div></div>
            <div className="card"><div className="metric-title">All applications</div><div className="metric-value">{applications.length}</div><div className="metric-foot">Across all stages</div></div>
          </div>
          <div className="card" style={{ marginBottom: 16 }}><div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}><select className="filter" aria-label="Saved applicant views" value={activeView} onChange={(event) => applyView(event.target.value)}><option>All applicants</option>{savedViews.map((view) => <option key={view.name}>{view.name}</option>)}</select><button className="btn" onClick={saveView}>+ Add view</button><select className="filter" aria-label="Filter applicant status" value={status} onChange={(event) => { setStatus(event.target.value as "all" | ApplicationStatus); setPage(1); }}><option value="all">All statuses</option>{stages.map((item) => <option key={item.stage_key} value={item.stage_key}>{item.label}</option>)}</select><select className="filter" aria-label="Filter application source" value={sourceFilter} onChange={(event) => { setSourceFilter(event.target.value); setPage(1); }}><option value="all">All sources</option>{sourceOptions.map((item) => <option key={item} value={item}>{item.replaceAll("_", " ")}</option>)}</select><span className="muted-small">{filtered.length} application{filtered.length === 1 ? "" : "s"}</span></div></div>
          {message && <div className="notice">{message}</div>}
          {canManageAssignments && slaPolicy && <form className="card" style={{ marginBottom: 16 }} onSubmit={(event) => void saveSlaPolicy(event)}>
            <div className="card-head"><span className="card-title">Recruitment SLA policy</span><label style={{ display: "flex", gap: 8, alignItems: "center" }}><input type="checkbox" checked={slaPolicy.enabled} onChange={(event) => setSlaPolicy({ ...slaPolicy, enabled: event.target.checked })} /> Enabled</label></div>
            <p className="muted-small">Configure internal response targets for your recruitment team. These are operational targets, not legal deadlines.</p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
              <label>Initial review (minutes)<input type="number" min="1" max="43200" required value={slaPolicy.initial_review_minutes} onChange={(event) => setSlaPolicy({ ...slaPolicy, initial_review_minutes: Number(event.target.value) })} /></label>
              <label>First recruiter action (minutes)<input type="number" min="1" max="43200" required value={slaPolicy.first_recruiter_action_minutes} onChange={(event) => setSlaPolicy({ ...slaPolicy, first_recruiter_action_minutes: Number(event.target.value) })} /></label>
              <label>Candidate follow-up (minutes)<input type="number" min="1" max="43200" required value={slaPolicy.candidate_follow_up_minutes} onChange={(event) => setSlaPolicy({ ...slaPolicy, candidate_follow_up_minutes: Number(event.target.value) })} /></label>
              <label>Post-interview update (minutes)<input type="number" min="1" max="43200" required value={slaPolicy.post_interview_update_minutes} onChange={(event) => setSlaPolicy({ ...slaPolicy, post_interview_update_minutes: Number(event.target.value) })} /></label>
              <label>Time zone<input required maxLength={100} value={slaPolicy.timezone} onChange={(event) => setSlaPolicy({ ...slaPolicy, timezone: event.target.value })} placeholder="Europe/London" /></label>
              <label>Business day handling<select value={slaPolicy.business_days_only ? "true" : "false"} onChange={(event) => setSlaPolicy({ ...slaPolicy, business_days_only: event.target.value === "true" })}><option value="true">Working days only</option><option value="false">All calendar days</option></select></label>
              <label>Business hours start<input type="time" required value={slaPolicy.business_hours_start} onChange={(event) => setSlaPolicy({ ...slaPolicy, business_hours_start: event.target.value })} /></label>
              <label>Business hours end<input type="time" required value={slaPolicy.business_hours_end} onChange={(event) => setSlaPolicy({ ...slaPolicy, business_hours_end: event.target.value })} /></label>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}><button className="btn primary" disabled={savingSlaPolicy}>{savingSlaPolicy ? "Saving..." : "Save SLA policy"}</button></div>
          </form>}

          {showCreate && (
            <div className="modal-backdrop">
              <form className="modal" onSubmit={async (event) => {
                event.preventDefault();
                if (!selectedJob || !selectedCandidate) { setMessage("Select both a job and candidate."); return; }
                setSaving(true);
                try {
                  const organizationId = getActiveOrganizationId(DEFAULT_ORGANIZATION_ID);
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
                  <span className="card-title">Create application</span>
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
            {stages.filter((stage) => stage.enabled || filtered.some((application) => application.status === stage.stage_key)).map((stage) => {
              const stageKey = stage.stage_key;
              const stageApps = filtered.filter((application) => application.status === stageKey);
              return (
                <div key={stageKey} className="pipeline-column" onDragOver={(event) => event.preventDefault()} onDrop={(event) => onDrop(event, stageKey)}>
                  <div className="pipeline-column-head">
                    <span>{stage.label}</span>
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
                            <option value={application.status}>{stageLabel(application.status)}</option>
                            {(stageMap.get(application.status)?.allowed_next_stages ?? []).filter((next) => stageMap.get(next)?.enabled).map((next) => (
                              <option key={next} value={next}>{stageLabel(next)}</option>
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
            <div className="card-head"><span className="card-title">Applications</span><span className="muted-small">{loading ? "Loading..." : "Live data · " + filtered.length + " records"}</span></div>
            {selectedApplicationIds.length > 0 && <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", padding: "12px 0" }}>
              <strong>{selectedApplicationIds.length} selected</strong>
              <select className="filter" aria-label="Bulk move selected applications to stage" value={bulkStatus} onChange={(event) => setBulkStatus(event.target.value as ApplicationStatus | "")}>
                <option value="">Move selected to stage...</option>
                {stages.filter((stage) => stage.enabled).map((stage) => <option key={stage.stage_key} value={stage.stage_key}>{stage.label}</option>)}
              </select>
              <button className="btn primary" disabled={!bulkStatus || bulkSaving} onClick={() => void runBulkTransition()}>{bulkSaving ? "Updating..." : "Apply to selected"}</button>
              <button className="btn" disabled={bulkSaving} onClick={() => setSelectedApplicationIds([])}>Clear selection</button>
              <span className="muted-small">Up to 100 applications per batch. Invalid transitions are reported individually.</span>
            </div>}
            <div style={{ overflowX: "auto" }}><table className="table applicant-table">
              <thead><tr><th><input type="checkbox" aria-label="Select all applications on this page" checked={pageApplications.length > 0 && pageApplications.every((item) => selectedApplicationIds.includes(item.id))} onChange={(event) => {
                if (event.target.checked) {
                  const next = Array.from(new Set([...selectedApplicationIds, ...pageApplications.map((item) => item.id)]));
                  if (next.length > 100) { setMessage("You can select up to 100 applications per batch."); return; }
                  setSelectedApplicationIds(next);
                } else {
                  const pageIds = new Set(pageApplications.map((item) => item.id));
                  setSelectedApplicationIds(selectedApplicationIds.filter((id) => !pageIds.has(id)));
                }
              }} /></th><th>Applicant ID</th><th><button className="table-sort" onClick={() => changeSort("candidate")}>Applicant name {sortBy === "candidate" ? (sortDirection === "asc" ? "↑" : "↓") : ""}</button></th><th>Email address</th><th>Mobile number</th><th>City / region</th><th><button className="table-sort" onClick={() => changeSort("source")}>Source {sortBy === "source" ? (sortDirection === "asc" ? "↑" : "↓") : ""}</button></th><th><button className="table-sort" onClick={() => changeSort("status")}>Applicant status {sortBy === "status" ? (sortDirection === "asc" ? "↑" : "↓") : ""}</button></th><th><button className="table-sort" onClick={() => changeSort("job")}>Job title {sortBy === "job" ? (sortDirection === "asc" ? "↑" : "↓") : ""}</button></th><th>Match / review</th>{canManageAssignments && <th>Assigned recruiter</th>}<th><button className="table-sort" onClick={() => changeSort("created")}>Applied {sortBy === "created" ? (sortDirection === "asc" ? "↑" : "↓") : ""}</button></th></tr></thead>
              <tbody>
                {loading ? <tr><td colSpan={canManageAssignments ? 12 : 11}>Loading applicants...</td></tr> : filtered.length === 0 ? <tr><td colSpan={canManageAssignments ? 12 : 11}>No applicants match these filters. Create a new application or adjust your search.</td></tr> : pageApplications.map((application) => {
                    const candidate = candidateMap.get(application.candidate_id);
                    const job = jobMap.get(application.job_id);
                    return (
                      <tr key={application.id}>
                        <td><input type="checkbox" aria-label={"Select " + candidateName(candidate)} checked={selectedApplicationIds.includes(application.id)} onChange={(event) => {
                          if (event.target.checked) {
                            if (selectedApplicationIds.length >= 100) { setMessage("You can select up to 100 applications per batch."); return; }
                            setSelectedApplicationIds((current) => current.includes(application.id) ? current : [...current, application.id]);
                          } else {
                            setSelectedApplicationIds((current) => current.filter((id) => id !== application.id));
                          }
                        }} /></td>
                        <td><Link className="link" href={"/submissions/" + application.id}>{application.id.slice(0, 8).toUpperCase()}</Link></td>
                        <td><Link className="link" href={"/submissions/" + application.id}><strong>{candidateName(candidate)}</strong></Link></td>
                        <td>{candidate?.email ?? "—"}</td><td>{candidate?.phone ?? "—"}</td><td>{[candidate?.city, candidate?.region].filter(Boolean).join(", ") || "—"}</td><td>{application.source || "Direct"}</td>
                        <td><select className="filter" aria-label={"Status for " + candidateName(candidate)} value={application.status} onChange={(event) => void changeStatus(application, event.target.value as ApplicationStatus)}><option value={application.status}>{application.status.replaceAll("_", " ")}</option>{(stageMap.get(application.status)?.allowed_next_stages ?? []).filter((next) => stageMap.get(next)?.enabled).map((next) => <option key={next} value={next}>{stageLabel(next)}</option>)}</select></td>
                        <td>{job?.title ?? "Unknown job"}</td><td>{application.match_score != null ? <span className="badge green">{application.match_score}% match</span> : <span className={"badge " + (application.human_reviewed ? "green" : "amber")}>{application.human_reviewed ? "Reviewed" : "Needs review"}</span>}</td>{canManageAssignments && <td><select className="filter" aria-label={"Assigned recruiter for " + candidateName(candidate)} value={assignments[application.id] ?? ""} disabled={savingAssignmentId === application.id} onChange={(event) => void changeAssignment(application, event.target.value)}><option value="">Unassigned</option>{recruiters.map((recruiter) => <option key={recruiter.id} value={recruiter.id}>{recruiter.full_name || recruiter.email || recruiter.id.slice(0, 8)}</option>)}</select></td>}<td>{new Date(application.created_at).toLocaleDateString()}</td>
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
