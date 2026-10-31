"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiFetch, API_BASE } from "@/lib/api";

type Article = {
  id: string;
  slug: string;
  title: string;
  category: string;
  summary: string;
  body_markdown: string;
  version: number;
};

export default function HelpPage() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [articles, setArticles] = useState<Article[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  const load = useCallback(async (search: string, selectedCategory: string) => {
    if (!API_BASE) {
      setMessage("The help API is not configured for this environment.");
      setLoading(false);
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      const params = new URLSearchParams();
      if (search.trim()) params.set("q", search.trim());
      if (selectedCategory) params.set("category", selectedCategory);
      const response = await apiFetch(API_BASE + "/api/help?" + params.toString());
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || "Unable to load help articles.");
      setArticles(body.articles ?? []);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load help articles.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load("", ""); }, [load]);

  function search(event: FormEvent) {
    event.preventDefault();
    void load(query, category);
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <Link href="/" className="brand">AQERITH<span>.</span></Link>
        <div className="nav-label">Workspace</div>
        <Link href="/" className="nav-item">Overview</Link>
        <Link href="/jobs" className="nav-item">Jobs</Link>
        <Link href="/candidates" className="nav-item">Candidates</Link>
        <Link href="/clients" className="nav-item">Clients</Link>
        <div className="nav-label">Account</div>
        <Link href="/settings" className="nav-item">Organisation settings</Link>
        <Link href="/billing" className="nav-item">Plans & billing</Link>
        <Link href="/help" className="nav-item active" aria-current="page">Help centre</Link>
        <Link href="/onboarding/checklist" className="nav-item">Getting started</Link>
      </aside>
      <main className="main">
        <header className="topbar"><div><strong>Help centre</strong><div className="muted-small">Guidance for your recruitment workspace</div></div><Link href="/" className="btn">Back to workspace</Link></header>
        <section className="content">
          <div className="eyebrow">Product guidance</div>
          <h1>How can we help?</h1>
          <p className="subtitle">Search practical guidance for common recruitment and workspace tasks.</p>
          <form onSubmit={search} className="card" style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 20 }}>
            <label style={{ flex: "1 1 260px" }}>Search help<input className="filter" style={{ width: "100%", marginTop: 6 }} value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Try “settings”, “candidate” or “job”" /></label>
            <label>Category<select className="filter" style={{ display: "block", marginTop: 6 }} value={category} onChange={(e) => setCategory(e.target.value)}><option value="">All topics</option><option>Jobs</option><option>Candidates</option><option>Settings</option><option>Security</option></select></label>
            <button className="btn primary" type="submit">Search</button>
          </form>
          {message && <div className="notice" role="status">{message}</div>}
          {loading ? <div className="card">Searching help articles…</div> : articles.length === 0 ? <div className="card">No matching articles. Try a broader search.</div> : (
            <div style={{ display: "grid", gap: 16 }}>
              {articles.map((article) => (
                <article className="card" key={article.id}>
                  <div className="eyebrow">{article.category} · v{article.version}</div>
                  <h2 className="card-title" style={{ margin: "8px 0" }}>{article.title}</h2>
                  <p className="subtitle" style={{ marginBottom: 14 }}>{article.summary}</p>
                  <details>
                    <summary className="link" style={{ cursor: "pointer" }}>Read guidance</summary>
                    <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontFamily: "inherit", fontSize: 14, lineHeight: 1.7, marginTop: 12 }}>{article.body_markdown}</pre>
                  </details>
                </article>
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
