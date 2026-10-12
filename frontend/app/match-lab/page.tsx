"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";
const DEFAULT_ORG = process.env.NEXT_PUBLIC_ORGANIZATION_ID ?? "";

type Job = { id: string; title: string; status: string; required_skills?: string[]; client?: string | null; location?: string | null };
type Candidate = { id: string; first_name: string; last_name?: string | null; current_title?: string | null; skills?: string[]; city?: string | null; region?: string | null; status?: string };

function normalizeSkill(value: string) {
  return value.trim().toLocaleLowerCase();
}

export default function MatchLabPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selectedJobId, setSelectedJobId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const org = window.localStorage.getItem("aqerith_active_org")
      || window.localStorage.getItem("talentos_active_org")
      || DEFAULT_ORG;
    const requestedJobId = new URLSearchParams(window.location.search).get("job_id") ?? "";
    setSelectedJobId(requestedJobId);
    if (!API_BASE || !org) {
      setError("Select an organisation to find candidate matches.");
      setLoading(false);
      return;
    }
    let cancelled = false;
    async function load() {
      try {
        const query = "organization_id=" + encodeURIComponent(org);
        const [jobResponse, candidateResponse] = await Promise.all([
          apiFetch(API_BASE + "/api/jobs?" + query),
          apiFetch(API_BASE + "/api/candidates?" + query),
        ]);
        if (!jobResponse.ok || !candidateResponse.ok) {
          throw new Error("Unable to load vacancies and candidates. Please retry.");
        }
        const [jobData, candidateData] = await Promise.all([jobResponse.json(), candidateResponse.json()]);
        if (!cancelled) {
          setJobs(Array.isArray(jobData) ? jobData : []);
          setCandidates(Array.isArray(candidateData) ? candidateData : []);
        }
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "Unable to load matching data.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, []);

  const selectedJob = jobs.find((job) => job.id === selectedJobId);
  const rankedCandidates = useMemo(() => {
    if (!selectedJob) return [];
    const required = Array.from(new Set((selectedJob.required_skills ?? []).map(normalizeSkill).filter(Boolean)));
    return candidates
      .filter((candidate) => candidate.status !== "inactive" && candidate.status !== "do_not_contact")
      .map((candidate) => {
        const candidateSkills = new Set((candidate.skills ?? []).map(normalizeSkill).filter(Boolean));
        const matchedSkills = required.filter((skill) => candidateSkills.has(skill));
        const score = required.length ? Math.round((matchedSkills.length / required.length) * 100) : null;
        return { candidate, matchedSkills, score, missingSkills: required.filter((skill) => !candidateSkills.has(skill)) };
      })
      .sort((a, b) => (b.score ?? -1) - (a.score ?? -1) || a.candidate.first_name.localeCompare(b.candidate.first_name));
  }, [candidates, selectedJob]);

  return (
    <main className="content">
      <div className="header-row">
        <div>
          <div className="eyebrow">Recruitment operations</div>
          <h1>Match Lab</h1>
          <p className="subtitle">Compare candidate skills against a vacancy's required skills. Recruiters make the final decision.</p>
        </div>
        <Link href="/dashboard" className="btn">Back to dashboard</Link>
      </div>

      {error && <div className="dashboard-error" role="alert"><div><strong>Matching workspace unavailable</strong><p>{error}</p></div><button className="btn" onClick={() => window.location.reload()}>Retry</button></div>}

      <section className="card" style={{ marginTop: 20, padding: 20 }}>
        <label htmlFor="match-job-select">Vacancy</label>
        <select id="match-job-select" value={selectedJobId} onChange={(event) => setSelectedJobId(event.target.value)} disabled={loading} style={{ display: "block", width: "100%", maxWidth: 640, marginTop: 8, padding: 12 }}>
          <option value="">Choose a vacancy</option>
          {jobs.filter((job) => job.status === "open").map((job) => <option key={job.id} value={job.id}>{job.title}{job.client ? " — " + job.client : ""}</option>)}
        </select>
        {selectedJob && <p className="muted-small" style={{ marginTop: 10 }}>Required skills: {(selectedJob.required_skills ?? []).join(", ") || "No required skills configured"}</p>}
      </section>

      <section className="card" style={{ marginTop: 20, padding: 20 }}>
        <div className="card-head"><span className="card-title">Candidate skill comparison</span><span className="muted-small">{selectedJob ? rankedCandidates.length + " candidates" : "Select a vacancy"}</span></div>
        <p className="muted-small">The percentage is the share of the vacancy's listed required skills found on a candidate profile. It is a transparent skills overlap indicator, not an AI prediction or hiring recommendation. Review profiles and follow your organisation's fair hiring process.</p>
        {loading ? <div className="dashboard-loading-lines"><span /><span /><span /></div> : !selectedJobId ? <div className="dashboard-empty"><strong>Choose a vacancy to begin</strong><p>Matches will be calculated from the selected vacancy's required skills.</p></div> : !selectedJob ? <div className="dashboard-empty"><strong>Vacancy not found</strong><p>Choose an available vacancy from your organisation.</p></div> : !rankedCandidates.length ? <div className="dashboard-empty"><strong>No candidates to compare</strong><p>Add candidate profiles with skills to see comparisons.</p></div> : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead><tr className="border-b"><th className="p-3">Candidate</th><th className="p-3">Skills overlap</th><th className="p-3">Matched skills</th><th className="p-3">Skills to review</th><th className="p-3">Profile</th></tr></thead>
              <tbody>{rankedCandidates.map(({ candidate, matchedSkills, score, missingSkills }) => <tr key={candidate.id} className="border-b">
                <td className="p-3"><strong>{[candidate.first_name, candidate.last_name].filter(Boolean).join(" ") || "Unnamed candidate"}</strong><div className="muted-small">{candidate.current_title || "Title not provided"}</div></td>
                <td className="p-3">{score === null ? "Not scored — vacancy has no required skills" : score + "%"}</td>
                <td className="p-3">{matchedSkills.join(", ") || "None listed"}</td>
                <td className="p-3">{missingSkills.join(", ") || (score === null ? "Add required skills to vacancy" : "No listed gaps")}</td>
                <td className="p-3"><Link className="link" href={"/candidates/" + candidate.id}>View profile</Link></td>
              </tr>)}</tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
