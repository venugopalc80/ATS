import type { MetadataRoute } from "next";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";
const ORGANIZATION_ID = process.env.NEXT_PUBLIC_ORGANIZATION_ID ?? "";

type PublicJob = { id: string; updated_at?: string };

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const baseUrl = process.env.NEXT_PUBLIC_SITE_URL?.replace(/\/$/, "") ?? "https://ats-frontend-the-pixel-muses.vercel.app";
  const entries: MetadataRoute.Sitemap = [
    { url: `${baseUrl}/careers`, changeFrequency: "hourly", priority: 0.8 },
  ];

  if (!API_BASE || !ORGANIZATION_ID) return entries;
  try {
    const response = await fetch(`${API_BASE}/api/public/jobs?organization_id=${encodeURIComponent(ORGANIZATION_ID)}`, { next: { revalidate: 300 } });
    if (!response.ok) return entries;
    const jobs: PublicJob[] = await response.json();
    return entries.concat(jobs.map((job) => ({
      url: `${baseUrl}/careers/${job.id}`,
      lastModified: job.updated_at ? new Date(job.updated_at) : new Date(),
      changeFrequency: "weekly" as const,
      priority: 0.7,
    })));
  } catch {
    return entries;
  }
}
