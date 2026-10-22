"use client";

import { FormEvent, useEffect, useState } from "react";
import { API_BASE, apiFetch } from "@/lib/api";
import { getActiveOrganizationId } from "@/lib/organization";

type RecordType = "candidates" | "applications" | "jobs" | "documents";
type SearchItem = Record<string, unknown>;
type SavedSearch = {
  id: string;
  name: string;
  record_type: RecordType;
  criteria: Record<string, unknown>;
  is_shared: boolean;
  updated_at: string;
};

export default function AdvancedSearchPage() {
  const [organizationId, setOrganizationId] = useState("");
  const [recordType, setRecordType] = useState<RecordType>("candidates");
  const [query, setQuery] = useState("");
  const [skills, setSkills] = useState("");
  const [location, setLocation] = useState("");
  const [status, setStatus] = useState("");
  const [source, setSource] = useState("");
  const [recruiterId, setRecruiterId] = useState("");
  const [minExperience, setMinExperience] = useState("");
  const [maxExperience, setMaxExperience] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [items, setItems] = useState<SearchItem[]>([]);
  const [savedSearches, setSavedSearches] = useState<SavedSearch[]>([]);
  const [savedName, setSavedName] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  async function loadSavedSearches(orgId: string) {
    if (!API_BASE || !orgId) return;
    try {
      const response = await apiFetch(`${API_BASE}/api/saved-searches?organization_id=${encodeURIComponent(orgId)}`);
      if (!response.ok) throw new Error("Could not load saved searches.");
      setSavedSearches(await response.json());
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not load saved searches.");
    }
  }

  useEffect(() => {
    const orgId = getActiveOrganizationId();
    setOrganizationId(orgId);
    void loadSavedSearches(orgId);
  }, []);

  function criteria() {
    return {
      ...(query.trim() ? { q: query.trim() } : {}),
      ...(skills.trim() ? { skills: skills.split(",").map((value) => value.trim()).filter(Boolean) } : {}),
      ...(location.trim() ? { location: location.trim() } : {}),
      ...(status ? { status } : {}),
      ...(source.trim() ? { source: source.trim() } : {}),
      ...(recruiterId.trim() ? { recruiter_id: recruiterId.trim() } : {}),
      ...(minExperience ? { min_experience: Number(minExperience) } : {}),
      ...(maxExperience ? { max_experience: Number(maxExperience) } : {}),
      ...(dateFrom ? { date_from: new Date(dateFrom).toISOString() } : {}),
      ...(dateTo ? { date_to: new Date(dateTo).toISOString() } : {}),
    };
  }

  async function runSearch(event?: FormEvent) {
    event?.preventDefault();
    if (!organizationId) {
      setMessage("Choose an active organisation before searching.");
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      const params = new URLSearchParams({
        organization_id: organizationId,
        record_type: recordType,
        limit: "50",
        offset: "0",
      });
      const filter = criteria();
      for (const [key, value] of Object.entries(filter)) {
        if (Array.isArray(value)) value.forEach((item) => params.append(key, String(item)));
        else params.set(key, String(value));
      }
      const response = await apiFetch(`${API_BASE}/api/search?${params.toString()}`);
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Search failed.");
      setItems(body.items ?? []);
    } catch (error) {
      setItems([]);
      setMessage(error instanceof Error ? error.message : "Search failed.");
    } finally {
      setLoading(false);
    }
  }

  async function saveSearch(event: FormEvent) {
    event.preventDefault();
    if (!savedName.trim()) {
      setMessage("Give this search a name before saving.");
      return;
    }
    setSaving(true);
    setMessage("");
    try {
      const response = await apiFetch(`${API_BASE}/api/saved-searches`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          organization_id: organizationId,
          name: savedName.trim(),
          record_type: recordType,
          criteria: criteria(),
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Could not save this search.");
      setSavedName("");
      setMessage("Search saved.");
      await loadSavedSearches(organizationId);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not save this search.");
    } finally {
      setSaving(false);
    }
  }

  async function runSavedSearch(saved: SavedSearch) {
    setLoading(true);
    setMessage("");
    try {
      const params = new URLSearchParams({
        organization_id: organizationId,
        limit: "50",
        offset: "0",
      });
      const response = await apiFetch(`${API_BASE}/api/saved-searches/${saved.id}/results?${params.toString()}`);
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Saved search failed.");
      setRecordType(saved.record_type);
      setItems(body.items ?? []);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Saved search failed.");
    } finally {
      setLoading(false);
    }
  }

  function titleFor(item: SearchItem) {
    const candidateName = [item.first_name, item.last_name].filter(Boolean).join(" ");
    return String(item.candidate_name || candidateName || item.title || item.original_filename || item.id || "Record");
  }

  function subtitleFor(item: SearchItem) {
    const bits = [item.job_title, item.title, item.city, item.region, item.country_code, item.status, item.source]
      .filter((value) => typeof value === "string" && value.length > 0);
    return bits.join(" · ");
  }

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Section 4 · Search, talent pools and sourcing</p>
          <h1>Advanced search</h1>
          <p className="subtitle">Search recruitment records using validated filters. Results stay scoped to your active organisation.</p>
        </div>
      </header>

      {message && <div className="notice" role="status" style={{ marginBottom: 16 }}>{message}</div>}

      <section className="card" style={{ marginBottom: 20 }}>
        <div className="card-head"><span className="card-title">Search filters</span></div>
        <form onSubmit={runSearch}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
            <label>Record type
              <select value={recordType} onChange={(event) => setRecordType(event.target.value as RecordType)}>
                <option value="candidates">Candidates</option>
                <option value="applications">Applications</option>
                <option value="jobs">Jobs</option>
                <option value="documents">Document metadata</option>
              </select>
            </label>
            <label>Search terms
              <input value={query} maxLength={100} onChange={(event) => setQuery(event.target.value)} placeholder="Name, role, job title or filename" />
            </label>
            <label>Skills (comma-separated)
              <input value={skills} onChange={(event) => setSkills(event.target.value)} placeholder="Python, SQL" />
            </label>
            <label>Location
              <input value={location} maxLength={120} onChange={(event) => setLocation(event.target.value)} placeholder="City, region or country" />
            </label>
            <label>Status / stage
              <input value={status} maxLength={40} onChange={(event) => setStatus(event.target.value)} placeholder="Active, interview, open…" />
            </label>
            <label>Source (applications)
              <input value={source} maxLength={80} onChange={(event) => setSource(event.target.value)} placeholder="Referral, LinkedIn…" />
            </label>
            <label>Recruiter ID (UUID)
              <input value={recruiterId} onChange={(event) => setRecruiterId(event.target.value)} placeholder="Optional recruiter filter" />
            </label>
            <label>Minimum experience (years)
              <input type="number" min="0" max="80" step="0.5" value={minExperience} onChange={(event) => setMinExperience(event.target.value)} />
            </label>
            <label>Maximum experience (years)
              <input type="number" min="0" max="80" step="0.5" value={maxExperience} onChange={(event) => setMaxExperience(event.target.value)} />
            </label>
            <label>Created from
              <input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
            </label>
            <label>Created to
              <input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
            </label>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 16 }}>
            <button className="btn primary" disabled={loading}>{loading ? "Searching…" : "Search records"}</button>
            <button className="btn" type="button" onClick={() => {
              setQuery(""); setSkills(""); setLocation(""); setStatus(""); setSource(""); setRecruiterId("");
              setMinExperience(""); setMaxExperience(""); setDateFrom(""); setDateTo(""); setItems([]);
            }}>Clear filters</button>
          </div>
        </form>
        <form onSubmit={saveSearch} style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 16 }}>
          <input aria-label="Saved search name" value={savedName} maxLength={120} onChange={(event) => setSavedName(event.target.value)} placeholder="Name this search" required style={{ maxWidth: 320 }} />
          <button className="btn" disabled={saving || !organizationId}>{saving ? "Saving…" : "Save filter"}</button>
        </form>
      </section>

      <section className="card" style={{ marginBottom: 20 }}>
        <div className="card-head"><span className="card-title">Saved searches</span><span className="muted-small">{savedSearches.length} available</span></div>
        {savedSearches.length === 0 ? <p className="muted-small">Your saved searches will appear here.</p> : (
          <div style={{ display: "grid", gap: 8 }}>
            {savedSearches.map((saved) => (
              <div key={saved.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap", padding: "10px 0", borderBottom: "1px solid var(--border, #e5e7eb)" }}>
                <div><strong>{saved.name}</strong><div className="muted-small">{saved.record_type} · {saved.is_shared ? "Shared" : "Private"}</div></div>
                <button type="button" className="btn" onClick={() => void runSavedSearch(saved)}>Run search</button>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="card">
        <div className="card-head"><span className="card-title">Results</span><span className="muted-small">{items.length} shown · maximum 50</span></div>
        {loading ? <p>Loading results…</p> : items.length === 0 ? <p className="muted-small">No results yet. Choose filters and run a search.</p> : (
          <div style={{ display: "grid", gap: 8 }}>
            {items.map((item, index) => (
              <article key={String(item.id ?? index)} style={{ padding: "12px 0", borderBottom: "1px solid var(--border, #e5e7eb)" }}>
                <strong>{titleFor(item)}</strong>
                <div className="muted-small">{subtitleFor(item) || String(item.record_type ?? recordType)}</div>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
