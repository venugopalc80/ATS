"use client";

import { FormEvent, useEffect, useState } from "react";
import { API_BASE, apiFetch } from "@/lib/api";
import { getActiveOrganizationId } from "@/lib/organization";

type Pool = { id: string; name: string; description?: string | null; visibility: "restricted" | "organisation"; member_count?: number };
type PoolMember = { id: string; candidate_id: string; first_name: string; last_name?: string | null; current_title?: string | null; status: string; expires_at?: string | null };

export default function TalentPoolsPage() {
  const [organizationId, setOrganizationId] = useState("");
  const [pools, setPools] = useState<Pool[]>([]);
  const [selectedPool, setSelectedPool] = useState("");
  const [members, setMembers] = useState<PoolMember[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [visibility, setVisibility] = useState<"restricted" | "organisation">("restricted");
  const [candidateId, setCandidateId] = useState("");
  const [purpose, setPurpose] = useState("Future recruitment opportunity");
  const [processingBasis, setProcessingBasis] = useState("legitimate_interests");
  const [expiry, setExpiry] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  async function loadPools(orgId: string) {
    if (!API_BASE || !orgId) return;
    const response = await apiFetch(`${API_BASE}/api/talent-pools?organization_id=${encodeURIComponent(orgId)}`);
    const body = await response.json();
    if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Could not load talent pools.");
    const list = body as Pool[];
    setPools(list);
    if (!selectedPool && list.length) setSelectedPool(list[0].id);
  }

  async function loadMembers(poolId: string, orgId = organizationId) {
    if (!poolId || !orgId) return;
    const response = await apiFetch(`${API_BASE}/api/talent-pools/${poolId}/members?organization_id=${encodeURIComponent(orgId)}`);
    const body = await response.json();
    if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Could not load pool members.");
    setMembers(body as PoolMember[]);
  }

  useEffect(() => {
    const orgId = getActiveOrganizationId();
    setOrganizationId(orgId);
    void loadPools(orgId).catch((error) => setMessage(error instanceof Error ? error.message : "Could not load talent pools."));
  }, []);

  useEffect(() => {
    if (selectedPool && organizationId) {
      void loadMembers(selectedPool, organizationId).catch((error) => setMessage(error instanceof Error ? error.message : "Could not load pool members."));
    }
  }, [selectedPool, organizationId]);

  async function createPool(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setMessage("");
    try {
      const response = await apiFetch(`${API_BASE}/api/talent-pools`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ organization_id: organizationId, name: name.trim(), description: description.trim() || null, visibility }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Could not create the pool.");
      setName(""); setDescription(""); setSelectedPool(body.id);
      await loadPools(organizationId);
      setMessage("Talent pool created.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not create the pool.");
    } finally {
      setLoading(false);
    }
  }

  async function addMember(event: FormEvent) {
    event.preventDefault();
    if (!selectedPool || !candidateId.trim() || !purpose.trim()) return;
    setLoading(true);
    setMessage("");
    try {
      const response = await apiFetch(`${API_BASE}/api/talent-pools/${selectedPool}/members`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          organization_id: organizationId,
          candidate_id: candidateId.trim(),
          purpose: purpose.trim(),
          processing_basis: processingBasis,
          ...(expiry ? { expires_at: new Date(expiry).toISOString() } : {}),
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Could not add candidate.");
      setCandidateId("");
      await loadMembers(selectedPool);
      await loadPools(organizationId);
      setMessage("Candidate added to the pool. The candidate profile was not duplicated.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not add candidate.");
    } finally {
      setLoading(false);
    }
  }

  async function removeMember(member: PoolMember) {
    const reason = window.prompt("Why is this candidate being removed from the pool?");
    if (!reason?.trim()) return;
    setLoading(true);
    try {
      const params = new URLSearchParams({ organization_id: organizationId, reason: reason.trim() });
      const response = await apiFetch(`${API_BASE}/api/talent-pools/${selectedPool}/members/${member.id}?${params.toString()}`, { method: "DELETE" });
      if (!response.ok) {
        const body = await response.json();
        throw new Error(typeof body.detail === "string" ? body.detail : "Could not remove pool membership.");
      }
      await loadMembers(selectedPool);
      await loadPools(organizationId);
      setMessage("Pool membership removed and recorded in the audit history.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not remove pool membership.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Section 4 · Candidate segmentation</p>
          <h1>Talent pools</h1>
          <p className="subtitle">Organise future candidates without creating duplicate profiles. Memberships record purpose, expiry and removal history.</p>
        </div>
      </header>
      {message && <div className="notice" role="status" style={{ marginBottom: 16 }}>{message}</div>}
      <section className="card" style={{ marginBottom: 20 }}>
        <div className="card-head"><span className="card-title">Create a pool</span></div>
        <form onSubmit={createPool}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 12 }}>
            <label>Pool name<input required maxLength={120} value={name} onChange={(event) => setName(event.target.value)} placeholder="Software Engineering" /></label>
            <label>Visibility<select value={visibility} onChange={(event) => setVisibility(event.target.value as typeof visibility)}><option value="restricted">Owner and authorised admins</option><option value="organisation">Organisation members</option></select></label>
          </div>
          <label>Description<textarea rows={2} maxLength={2000} value={description} onChange={(event) => setDescription(event.target.value)} /></label>
          <button className="btn primary" disabled={loading || !organizationId}>{loading ? "Saving…" : "Create pool"}</button>
        </form>
      </section>

      <section className="card" style={{ marginBottom: 20 }}>
        <div className="card-head"><span className="card-title">Pools</span><span className="muted-small">{pools.length} total</span></div>
        {pools.length === 0 ? <p className="muted-small">Create a pool to start organising candidates.</p> : (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {pools.map((pool) => <button key={pool.id} type="button" className={selectedPool === pool.id ? "btn primary" : "btn"} onClick={() => setSelectedPool(pool.id)}>{pool.name} · {pool.member_count ?? 0}</button>)}
          </div>
        )}
      </section>

      {selectedPool && (
        <>
          <section className="card" style={{ marginBottom: 20 }}>
            <div className="card-head"><span className="card-title">Add candidate to selected pool</span></div>
            <form onSubmit={addMember}>
              <label>Candidate ID<input required value={candidateId} onChange={(event) => setCandidateId(event.target.value)} placeholder="Candidate UUID from candidate profile" /></label>
              <label>Purpose for retaining this membership<input required maxLength={500} value={purpose} onChange={(event) => setPurpose(event.target.value)} /></label>
              <label>Processing basis<select required value={processingBasis} onChange={(event) => setProcessingBasis(event.target.value)}><option value="notice_and_consent">Notice and consent</option><option value="legitimate_interests">Legitimate interests</option><option value="contractual_necessity">Contractual necessity</option><option value="legal_obligation">Legal obligation</option><option value="public_task">Public task</option><option value="other_authorised_basis">Other authorised basis</option></select></label>
              <label>Membership expiry (optional)<input type="date" value={expiry} onChange={(event) => setExpiry(event.target.value)} /></label>
              <button className="btn primary" disabled={loading}>{loading ? "Saving…" : "Add to pool"}</button>
            </form>
          </section>
          <section className="card">
            <div className="card-head"><span className="card-title">Active members</span><span className="muted-small">{members.length} shown</span></div>
            {members.length === 0 ? <p className="muted-small">No active members in this pool yet.</p> : (
              <div style={{ overflowX: "auto" }}>
                <table className="table">
                  <thead><tr><th>Candidate</th><th>Current role</th><th>Location</th><th>Processing basis</th><th>Expiry</th><th>Action</th></tr></thead>
                  <tbody>{members.map((member) => <tr key={member.id}>
                    <td>{[member.first_name, member.last_name].filter(Boolean).join(" ")}</td>
                    <td>{member.current_title || "Not specified"}</td>
                    <td>{[member.city, member.region].filter(Boolean).join(", ") || "—"}</td>
                    <td>{member.processing_basis?.replaceAll("_", " ") || "Legacy record"}</td>
                    <td>{member.expires_at ? new Date(member.expires_at).toLocaleDateString() : "No membership expiry"}</td>
                    <td><button className="btn" disabled={loading} onClick={() => void removeMember(member)}>Remove</button></td>
                  </tr>)}</tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </main>
  );
}
