'use client';

import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { useEffect, useMemo, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
const ORGANIZATION_ID = process.env.NEXT_PUBLIC_ORGANIZATION_ID;

type Job = { id: string; title: string; status: string };
type Candidate = { id: string; first_name: string; last_name?: string | null; current_title?: string | null };
type Application = {
  id: string;
  job_id: string;
  candidate_id: string;
  source?: string | null;
  status: "new" | "screening" | "submitted" | "interview" | "offer" | "hired" | "rejected" | "withdrawn";
  match_score?: number | null;
  human_reviewed: boolean;
  created_at: string;
};

const statuses = ["new", "screening", "submitted", "interview", "offer", "hired", "rejected", "withdrawn"];

function name(c: Candidate) {
  return [c.first_name, c.last_name].filter(Boolean).join(" ");
}

export default function SubmissionsPage() {
  const [applications, setApplications] = useState<Application[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [status, setStatus] = useState("all");
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  const jobMap = useMemo(() => new Map(jobs.map((job) => [job.id, job])), [jobs]);
  const candidateMap = useMemo(() => new Map(candidates.map((candidate) => [candidate.id, candidate])), [candidates]);

  useEffect(() => {
    if (!API_BASE || !ORGANIZATION_ID) {
      setLoading(false);
      setMessage("API configuration is missing.");
      return;
    }

    async function load() {
      try {
        const org = encodeURIComponent(ORGANIZATION_ID);
        const [appsResponse, jobsResponse, candidatesResponse] = await Promise.all([
          apiFetch(API_BASE + "/api/applications?organization_id=" + org),
          apiFetch(API_BASE + "/api/jobs?organization_id=" + org),
          apiFetch(API_BASE + "/api/candidates?organization_id=" + org),
        ]);

        if (!appsResponse.ok || !jobsResponse.ok || !candidatesResponse.ok) {
          throw new Error("Unable to load recruitment pipeline.");
        }

        setApplications(await appsResponse.json());
        setJobs(await jobsResponse.json());
        setCandidates(await candidatesResponse.json());
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

  async function changeStatus(application: Application, nextStatus: Application["status"]) {
    try {
      const response = await apiFetch(API_BASE + "/api/applications/" + application.id, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: nextStatus }),
      });
      if (!response.ok) throw new Error("Unable to update application.");
      const updated: Application = await response.json();
      setApplications((current) => current.map((item) => item.id === updated.id ? updated : item));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to update application.");
    }
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
        {["Interviews", "Clients", "Vendors", "Talent Bench", "Onboarding", "Placements", "Leads", "Reports"].map((item) => (
          <div key={item} className="nav-item"><span>•</span><span>{item}</span></div>
        ))}
        <div className="nav-label">Administration</div>
        <div className="nav-item"><span>⚙</span><span>Settings</span></div>
      </aside>

      <main className="main">
        <header className="topbar">
          <input className="search" placeholder="Search submissions..." />
          <div className="profile"><span>Acme Recruitment</span><div className="avatar">VG</div></div>
        </header>

        <section className="content">
          <div className="header-row">
            <div>
              <div className="eyebrow">Recruitment pipeline</div>
              <h1>Submissions</h1>
              <p className="subtitle">Move candidates through screening, submission, interview and offer stages.</p>
            </div>
            <select className="filter" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="all">All statuses</option>
              {statuses.map((item) => <option key={item} value={item}>{item.replaceAll("_", " ")}</option>)}
            </select>
          </div>

          {message && <div className="notice">{message}</div>}

          <div className="card">
            <div className="card-head">
              <span className="card-title">Applications</span>
              <span className="muted-small">{loading ? "Loading..." : filtered.length + " application" + (filtered.length === 1 ? "" : "s")}</span>
            </div>

            <table className="table">
              <thead><tr><th>Candidate</th><th>Position</th><th>Current role</th><th>Status</th><th>Match</th><th>Review</th><th>Created</th></tr></thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={7}>Loading pipeline...</td></tr>
                ) : filtered.length === 0 ? (
                  <tr><td colSpan={7}>No applications yet.</td></tr>
                ) : filtered.map((application) => {
                  const candidate = candidateMap.get(application.candidate_id);
                  const job = jobMap.get(application.job_id);
                  return (
                    <tr key={application.id}>
                      <td><strong>{candidate ? name(candidate) : "Unknown candidate"}</strong></td>
                      <td>{job?.title ?? "Unknown job"}</td>
                      <td>{candidate?.current_title ?? "-"}</td>
                      <td>
                        <select className="filter" value={application.status} onChange={(e) => changeStatus(application, e.target.value as Application["status"])}>
                          {statuses.map((item) => <option key={item} value={item}>{item.replaceAll("_", " ")}</option>)}
                        </select>
                      </td>
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
