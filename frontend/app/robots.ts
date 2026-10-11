import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  const baseUrl = process.env.NEXT_PUBLIC_SITE_URL?.replace(/\/$/, "") ?? "https://aqerith.com";

  return {
    rules: [
      {
        userAgent: "*",
        allow: ["/careers", "/careers/"],
        disallow: ["/dashboard", "/login", "/api/"],
      },
    ],
    sitemap: `${baseUrl}/sitemap.xml`,
    host: baseUrl,
  };
}
