import Link from "next/link";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import PublicApplyForm from "./apply-form";

type PublicJob = {
  id: string;
  title: string;
  description?: string | null;
  location?: string | null;
  country_code?: string | null;
  employment_type?: string | null;
  work_mode?: string | null;
  salary_min?: number | string | null;
  salary_max?: number | string | null;
  salary_currency?: string | null;
  required_skills?: string[];
  created_at?: string;
  updated_at?: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";
const ORGANIZATION_ID = process.env.NEXT_PUBLIC_ORGANIZATION_ID ?? "";

async function getJob(jobId: string): Promise<PublicJob | null> {
  if (!API_BASE || !ORGANIZATION_ID) return null;
  try {
    const response = await fetch(`${API_BASE}/api/public/jobs/${encodeURIComponent(jobId)}?organization_id=${encodeURIComponent(ORGANIZATION_ID)}`, { next: { revalidate: 60 } });
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

export async function generateMetadata({ params }: { params: Promise<{ jobId: string }> }): Promise<Metadata> {
  const { jobId } = await params;
  const job = await getJob(jobId);
  if (!job) return { title: "Job not found | TalentOS Careers", robots: { index: false, follow: false } };
  return {
    title: `${job.title} | TalentOS Careers`,
    description: (job.description ?? `Explore the ${job.title} opportunity.`).replace(/<[^>]*>/g, " ").slice(0, 155),
    alternates: { canonical: `/careers/${job.id}` },
    robots: { index: true, follow: true },
  };
}

function plainText(value: string) {
  return value.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}

export default async function CareerJobPage({ params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = await params;
  const job = await getJob(jobId);
  if (!job) notFound();

  const baseUrl = process.env.NEXT_PUBLIC_SITE_URL?.replace(/\/$/, "") ?? "https://ats-frontend-the-pixel-muses.vercel.app";
  const jobUrl = `${baseUrl}/careers/${job.id}`;
  const salaryMin = job.salary_min == null ? undefined : Number(job.salary_min);
  const salaryMax = job.salary_max == null ? undefined : Number(job.salary_max);
  const schema = {
    "@context": "https://schema.org",
    "@type": "JobPosting",
    title: job.title,
    description: plainText(job.description ?? job.title),
    identifier: { "@type": "PropertyValue", name: "TalentOS", value: job.id },
    datePosted: job.created_at ? new Date(job.created_at).toISOString() : undefined,
    dateModified: job.updated_at ? new Date(job.updated_at).toISOString() : undefined,
    employmentType: job.employment_type?.toUpperCase().replace(/[ -]+/g, "_"),
    directApply: true,
    url: jobUrl,
    hiringOrganization: {
      "@type": "Organization",
      name: "TalentOS Careers",
      sameAs: baseUrl,
    },
    jobLocation: job.location ? {
      "@type": "Place",
      address: { "@type": "PostalAddress", addressLocality: job.location, addressCountry: job.country_code },
    } : undefined,
    jobLocationType: job.work_mode?.toLowerCase() === "remote" ? "TELECOMMUTE" : undefined,
    baseSalary: salaryMin !== undefined || salaryMax !== undefined ? {
      "@type": "MonetaryAmount",
      currency: job.salary_currency ?? "GBP",
      value: { "@type": "QuantitativeValue", minValue: salaryMin, maxValue: salaryMax, unitText: "YEAR" },
    } : undefined,
  };

  return (
    <main className="careers-page">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(schema).replace(/</g, "\\u003c") }} />
      <header className="careers-header">
        <Link href="/careers" className="careers-brand">Talent<span>OS</span> Careers</Link>
        <Link href="/careers" className="career-back-link">← All opportunities</Link>
      </header>
      <article className="career-detail">
        <p className="careers-eyebrow">OPEN POSITION</p>
        <h1>{job.title}</h1>
        <p className="career-detail-meta">{[job.location, job.work_mode, job.employment_type].filter(Boolean).join(" · ")}</p>
        {(salaryMin !== undefined || salaryMax !== undefined) ? <p className="career-salary">{salaryMin?.toLocaleString()} {salaryMin !== undefined && salaryMax !== undefined ? "–" : ""} {salaryMax?.toLocaleString()} {job.salary_currency ?? "GBP"}</p> : null}
        <div className="career-detail-content">{job.description ? <p>{plainText(job.description)}</p> : <p>Contact the recruitment team for further role details.</p>}</div>
        {job.required_skills?.length ? <section className="career-requirements"><h2>Skills and experience</h2><div className="career-skills">{job.required_skills.map(skill => <span key={skill}>{skill}</span>)}</div></section> : null}
        <PublicApplyForm jobId={job.id} />
        <Link className="career-view-link" href="/careers">Browse more roles <span aria-hidden="true">→</span></Link>
      </article>
      <footer className="careers-footer">Powered by TalentOS · Recruitment, made more human.</footer>
    </main>
  );
}
