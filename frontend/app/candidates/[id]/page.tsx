"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { apiFetch } from "@/lib/api";
import RecruiterNotes from "@/components/RecruiterNotes";
import CandidateDocuments from "@/components/CandidateDocuments";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";
const DEFAULT_ORG = process.env.NEXT_PUBLIC_ORGANIZATION_ID ?? "";

type Candidate = {
  id: string;
  first_name: string;
  last_name?: string | null;
  email?: string | null;
  phone?: string | null;
  city?: string | null;
  region?: string | null;
  country_code?: string | null;
  status: string;
  current_title?: string | null;
  years_experience?: number | null;
  skills: string[];
};
type Application = {
  id: string;
  candidate_id: string;
  job_id: string;
  status: string;
  match_score?: number | null;
  created_at: string;
};
type Job = { id: string; title: string };
type Interview = {
  id: string;
  application_id: string;
  scheduled_at: string;
  interview_type: string;
  status: string;
};
type Offer = {
  id: string;
  application_id: string;
  title: string;
  status: string;
  salary_amount?: number | null;
  salary_currency?: string | null;
  start_date?: string | null;
  created_at?: string | null;
};
type Placement = {
  id: string;
  candidate_id: string;
  job_id: string;
  status: string;
  start_date: string;
};

type TimelineEntry = {
  id: string;
  date: string | null;
  title: string;
  detail: string;
  kind: "Application" | "Interview" | "Offer" | "Placement";
};

function formatStatus(value: string) {
  return value.replaceAll("_", " ");
}

function formatDate(value: string | null) {
  if (!value || !Number.isFinite(Date.parse(value))) return "Date not recorded";
  return new Date(value).toLocaleString();
}

export default function Candidate360Page() {
  const { id } = useParams<{ id: string }>();
  const [candidate, setCandidate] = useState<Candidate | null>(null);
  const [apps, setApps] = useState<Application[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [interviews, setInterviews] = useState<Interview[]>([]);
  const [offers, setOffers] = useState<Offer[]>([]);
  const [placements, setPlacements] = useState<Placement[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  const org =
    typeof window !== "undefined"
      ? window.localStorage.getItem("aqerith_active_org") ||
        window.localStorage.getItem("talentos_active_org") ||
        DEFAULT_ORG
      : DEFAULT_ORG;

  const jobMap = useMemo(() => new Map(jobs.map((job) => [job.id, job])), [jobs]);
  const appMap = useMemo(() => new Map(apps.map((app) => [app.id, app])), [apps]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setMessage("");
      try {
        const organisation = encodeURIComponent(org);
        const candidateUrl = API_BASE + "/api/candidates/" + encodeURIComponent(id);
        const applicationsUrl =
          API_BASE +
          "/api/applications?organization_id=" +
          organisation +
          "&candidate_id=" +
          encodeURIComponent(id);

        const [candidateResponse, applicationsResponse] = await Promise.all([
          apiFetch(candidateUrl),
          apiFetch(applicationsUrl),
        ]);

        if (!candidateResponse.ok || !applicationsResponse.ok) {
          throw new Error("Unable to load candidate profile or applications.");
        }

        const candidateData: Candidate = await candidateResponse.json();
        const applicationData: Application[] = await applicationsResponse.json();
        const jobIds = [...new Set(applicationData.map((application) => application.job_id))].slice(0, 100);
        const jobFilter = jobIds.map((jobId) => "&job_ids=" + encodeURIComponent(jobId)).join("");

        const [jobsResponse, interviewsResponse, offersResponse, placementsResponse] =
          await Promise.all([
            jobIds.length
              ? apiFetch(API_BASE + "/api/jobs?organization_id=" + organisation + jobFilter)
              : Promise.resolve(new Response("[]", { status: 200 })),
            apiFetch(
              API_BASE +
                "/api/interviews?organization_id=" +
                organisation +
                "&candidate_id=" +
                encodeURIComponent(id),
            ),
            apiFetch(
              API_BASE +
                "/api/offers?organization_id=" +
                organisation +
                "&candidate_id=" +
                encodeURIComponent(id),
            ),
            apiFetch(
              API_BASE +
                "/api/placements?organization_id=" +
                organisation +
                "&candidate_id=" +
                encodeURIComponent(id),
            ),
          ]);

        if (
          !jobsResponse.ok ||
          !interviewsResponse.ok ||
          !offersResponse.ok ||
          !placementsResponse.ok
        ) {
          throw new Error("Unable to load candidate workflow details. Check your access permissions.");
        }

        const [jobData, interviewData, offerData, placementData] = await Promise.all([
          jobsResponse.json(),
          interviewsResponse.json(),
          offersResponse.json(),
          placementsResponse.json(),
        ]);

        if (cancelled) return;
        setCandidate(candidateData);
        setApps(applicationData);
        setJobs(jobData);
        setInterviews(interviewData);
        setOffers(offerData);
        setPlacements(placementData);
      } catch (error) {
        if (!cancelled) {
          setMessage(error instanceof Error ? error.message : "Unable to load candidate.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    if (id && org) void load();
    else {
      setMessage("Select an organisation before opening a candidate profile.");
      setLoading(false);
    }

    return () => {
      cancelled = true;
    };
  }, [id, org]);

  const candidateApps = useMemo(
    () => apps.filter((application) => application.candidate_id === id),
    [apps, id],
  );
  const candidateInterviews = useMemo(
    () => interviews.filter((interview) => appMap.has(interview.application_id)),
    [interviews, appMap],
  );
  const candidateOffers = useMemo(
    () => offers.filter((offer) => appMap.has(offer.application_id)),
    [offers, appMap],
  );
  const candidatePlacements = useMemo(
    () => placements.filter((placement) => placement.candidate_id === id),
    [placements, id],
  );

  const timeline = useMemo<TimelineEntry[]>(() => {
    const entries: TimelineEntry[] = [];

    candidateApps.forEach((application) => {
      entries.push({
        id: "application-" + application.id,
        date: application.created_at,
        title: "Application created",
        detail:
          (jobMap.get(application.job_id)?.title || "Unknown job") +
          " · " +
          formatStatus(application.status),
        kind: "Application",
      });
    });

    candidateInterviews.forEach((interview) => {
      const application = appMap.get(interview.application_id);
      entries.push({
        id: "interview-" + interview.id,
        date: interview.scheduled_at,
        title: "Interview",
        detail:
          (jobMap.get(application?.job_id || "")?.title || "Unknown job") +
          " · " +
          formatStatus(interview.interview_type) +
          " · " +
          formatStatus(interview.status),
        kind: "Interview",
      });
    });

    candidateOffers.forEach((offer) => {
      entries.push({
        id: "offer-" + offer.id,
        date: offer.created_at || offer.start_date || null,
        title: "Offer",
        detail:
          offer.title +
          " · " +
          formatStatus(offer.status) +
          (offer.salary_amount != null
            ? " · " + (offer.salary_currency || "") + " " + offer.salary_amount
            : ""),
        kind: "Offer",
      });
    });

    candidatePlacements.forEach((placement) => {
      entries.push({
        id: "placement-" + placement.id,
        date: placement.start_date || null,
        title: "Placement",
        detail:
          (jobMap.get(placement.job_id)?.title || "Unknown job") +
          " · " +
          formatStatus(placement.status),
        kind: "Placement",
      });
    });

    return entries.sort(
      (left, right) => (Date.parse(right.date || "") || 0) - (Date.parse(left.date || "") || 0),
    );
  }, [
    candidateApps,
    candidateInterviews,
    candidateOffers,
    candidatePlacements,
    appMap,
    jobMap,
  ]);

  if (loading) return <main className="p-8">Loading candidate...</main>;

  if (!candidate) {
    return (
      <main className="p-8">
        <Link href="/candidates">← Candidates</Link>
        <h1 className="mt-6 text-3xl font-semibold">Candidate not found</h1>
        <p className="mt-2 text-gray-500">{message}</p>
      </main>
    );
  }

  const name = [candidate.first_name, candidate.last_name].filter(Boolean).join(" ");

  return (
    <div className="shell">
      <aside className="sidebar">
        <Link href="/" className="brand">AQERITH</Link>
        <div className="nav-label">Workspace</div>
        <Link href="/candidates" className="nav-item active">● <span>Candidates</span></Link>
        <Link href="/submissions" className="nav-item">↗ <span>Applications Inbox</span></Link>
        <Link href="/interviews" className="nav-item">◷ <span>Interviews</span></Link>
        <Link href="/offers" className="nav-item">□ <span>Offers</span></Link>
        <Link href="/placements" className="nav-item">◈ <span>Placements</span></Link>
      </aside>

      <main className="main">
        <header className="topbar">
          <input className="search" placeholder="Search candidates..." aria-label="Search candidates" />
          <div className="profile">
            <span>Acme Recruitment</span>
            <div className="avatar">VG</div>
          </div>
        </header>

        <section className="content">
          <Link href="/candidates" className="text-sm text-gray-500">← Back to candidates</Link>
          <div className="header-row mt-4">
            <div>
              <div className="eyebrow">Candidate 360</div>
              <h1>{name}</h1>
              <p className="subtitle">
                {candidate.current_title || "Candidate"} · {formatStatus(candidate.status)}
              </p>
            </div>
            <Link href="/submissions" className="btn primary">View applications</Link>
          </div>

          {message && <div className="notice" role="status">{message}</div>}

          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <div className="card">
              <div className="card-title">Profile</div>
              <p className="mt-3">{candidate.email || "Contact details restricted or not recorded"}</p>
              <p>{candidate.phone || "No phone or access restricted"}</p>
              <p>
                {[candidate.city, candidate.region, candidate.country_code].filter(Boolean).join(", ") ||
                  "No location"}
              </p>
              <p>{candidate.years_experience ?? "—"} years experience</p>
            </div>
            <div className="card">
              <div className="card-title">Skills</div>
              <div className="mt-3">
                {candidate.skills.length ? candidate.skills.join(" · ") : "No skills recorded"}
              </div>
            </div>
            <div className="card">
              <div className="card-title">Pipeline</div>
              <p className="mt-3">{candidateApps.length} applications</p>
              <p>{candidateInterviews.length} interviews</p>
              <p>{candidateOffers.length} offers</p>
              <p>{candidatePlacements.length} placements</p>
            </div>
          </div>

          <CandidateDocuments candidateId={id} />

          <div className="card mt-5">
            <div className="card-head">
              <span className="card-title">Applications</span>
              <span className="muted-small">{candidateApps.length}</span>
            </div>
            <table className="table">
              <thead>
                <tr><th>Position</th><th>Status</th><th>Match</th><th>Created</th></tr>
              </thead>
              <tbody>
                {candidateApps.length ? candidateApps.map((application) => (
                  <tr key={application.id}>
                    <td>{jobMap.get(application.job_id)?.title || "Unknown job"}</td>
                    <td>{formatStatus(application.status)}</td>
                    <td>{application.match_score != null ? application.match_score + "%" : "Pending"}</td>
                    <td>{formatDate(application.created_at)}</td>
                  </tr>
                )) : (
                  <tr><td colSpan={4}>No applications.</td></tr>
                )}
              </tbody>
            </table>
          </div>

          <RecruiterNotes candidateId={id} />

          <div className="card mt-5">
            <div className="card-head">
              <span className="card-title">Recruitment timeline</span>
              <span className="muted-small">{timeline.length} events · newest first</span>
            </div>
            <div className="space-y-3">
              {timeline.length ? timeline.map((item) => (
                <div key={item.id} className="flex gap-3 border-b pb-3 last:border-b-0">
                  <div className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full bg-slate-400" aria-hidden="true" />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <strong>{item.title}</strong>
                      <span className="muted-small">{item.kind}</span>
                    </div>
                    <div className="mt-1">{item.detail}</div>
                    <div className="muted-small mt-1">{formatDate(item.date)}</div>
                  </div>
                </div>
              )) : (
                <div className="text-gray-500">
                  No recruitment activity recorded yet. Applications, interviews, offers and placements
                  will appear here as they happen.
                </div>
              )}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
