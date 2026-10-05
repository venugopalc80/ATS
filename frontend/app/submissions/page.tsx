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

  const filtered = useMemo(
    () => applications.filter((application) => status === "all" || application.status === status),
    [applications, status]
  );

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
          <input className="search" placeholder="Search submissions..." aria-label="Search submissions" />
          <div className="profile"><span>Acme Recruitment</span><div className="avatar">VG</div></div>
        </header>

        <section className="content">
          <div className="header-row">
            <div>
              <div className="eyebrow">Recruitment pipeline</div>
              <h1>Submissions</h1>
              <p className="subtitle">Move candidates through screening, submission, interview and offer stages.</p>
            </div>
            <button className="btn primary" onClick={() => { setMessage(""); setShowCreate(true); }}>+ New submission</button>
            <select className="filter" value={status} onChange={(event) => setStatus(event.target.value as "all" | ApplicationStatus)}>
              <option value="all">All statuses</option>
              {statuses.map((item) => <option key={item} value={item}>{item.replaceAll("_", " ")}</option>)}
            </select>
          </div>

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

          <div className="pipeline-board">
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
                          <strong>{candidateName(candidate)}</strong>
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
          </div>

          <div className="card">
            <div className="card-head">
              <span className="card-title">Application details</span>
              <span className="muted-small">{loading ? "Loading..." : filtered.length + " application" + (filtered.length === 1 ? "" : "s")}</span>
            </div>
            <table className="table">
              <thead><tr><th>Candidate</th><th>Position</th><th>Status</th><th>Match</th><th>Review</th><th>Created</th></tr></thead>
              <tbody>
                {loading ? <tr><td colSpan={6}>Loading pipeline...</td></tr> :
                  filtered.length === 0 ? <tr><td colSpan={6}>No applications yet.</td></tr> :
                  filtered.map((application) => {
                    const candidate = candidateMap.get(application.candidate_id);
                    const job = jobMap.get(application.job_id);
                    return (
                      <tr key={application.id}>
                        <td><strong>{candidateName(candidate)}</strong></td>
                        <td>{job?.title ?? "Unknown job"}</td>
                        <td>{application.status}</td>
                        <td>{application.match_score != null ? application.match_score + "%" : "Pending"}</td>
                        <td><span className={"badge " + (application.human_reviewed ? "green" : "amber")}>{application.human_reviewed ? "Reviewed" : "Needs review"}</span></td>
                        <td>{new Date(application.created_at).toLocaleDateString()}</td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </div>
  );
}
