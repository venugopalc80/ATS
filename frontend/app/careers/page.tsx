import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Careers | TalentOS",
  description: "Explore open opportunities published through TalentOS Careers.",
  robots: { index: true, follow: true },
};

type PublicJob = {
  id: string;
  title: string;
  description?: string | null;
  location?: string | null;
  employment_type?: string | null;
  work_mode?: string | null;
  salary_min?: number | string | null;
  salary_max?: number | string | null;
  salary_currency?: string | null;
  required_skills?: string[];
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";
const ORGANIZATION_ID = process.env.NEXT_PUBLIC_ORGANIZATION_ID ?? "";

async function getJobs(): Promise<PublicJob[]> {
  if (!API_BASE || !ORGANIZATION_ID) return [];
  try {
    const response = await fetch(`${API_BASE}/api/public/jobs?organization_id=${encodeURIComponent(ORGANIZATION_ID)}`, { next: { revalidate: 60 } });
    if (!response.ok) return [];
    return await response.json();
  } catch {
    return [];
  }
}

export default async function CareersPage() {
  const jobs = await getJobs();
  return (
    <main className="careers-page">
      <header className="careers-header">
        <Link href="/careers" className="careers-brand">Talent<span>OS</span> Careers</Link>
        <span>Opportunities, made clearer.</span>
      </header>
      <section className="careers-hero">
        <p className="careers-eyebrow">CAREERS AT OUR CLIENTS</p>
        <h1>Find your next opportunity.</h1>
        <p>Explore current openings and discover where your skills can make a difference.</p>
      </section>
      <section className="careers-list" aria-labelledby="open-roles-title">
        <div className="careers-section-heading">
          <div><p className="careers-eyebrow">OPEN POSITIONS</p><h2 id="open-roles-title">Current opportunities</h2></div>
          <span>{jobs.length} {jobs.length === 1 ? "role" : "roles"}</span>
        </div>
        {jobs.length ? jobs.map((job) => (
          <article className="career-job-card" key={job.id}>
            <div className="career-job-copy">
              <h3><Link href={`/careers/${job.id}`}>{job.title}</Link></h3>
              <p>{[job.location, job.work_mode, job.employment_type].filter(Boolean).join(" · ") || "Details on job page"}</p>
              {job.required_skills?.length ? <div className="career-skills">{job.required_skills.slice(0, 5).map(skill => <span key={skill}>{skill}</span>)}</div> : null}
            </div>
            <Link className="career-view-link" href={`/careers/${job.id}`}>View role <span aria-hidden="true">→</span></Link>
          </article>
        )) : <div className="careers-empty"><h3>No open roles just yet</h3><p>Please check back soon for new opportunities.</p></div>}
      </section>
      <footer className="careers-footer">Powered by TalentOS · Recruitment, made more human.</footer>
    </main>
  );
}
