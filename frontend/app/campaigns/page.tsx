"use client";

import { FormEvent, useEffect, useState } from "react";
import { API_BASE, apiFetch } from "@/lib/api";
import { getActiveOrganizationId } from "@/lib/organization";

type Campaign = {
  id: string;
  name: string;
  status: string;
  budget_amount?: number | null;
  budget_currency?: string | null;
  attributed_candidates: number;
  referrals: number;
  qualified_referrals: number;
  hired_referrals: number;
  qualified_applications: number;
  interview_progressed_applications: number;
  hired_applications: number;
  channel_spend?: number | null;
  channel_spend_currency?: string | null;
  cost_per_hire?: number | null;
};
type Referral = {
  id: string;
  campaign_id?: string | null;
  candidate_id?: string | null;
  referrer_name?: string | null;
  status: "received" | "reviewing" | "qualified" | "interviewing" | "hired" | "declined" | "withdrawn";
  received_at: string;
  notes?: string | null;
};

export default function RecruitmentCampaignsPage() {
  const [organizationId, setOrganizationId] = useState("");
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedCampaign, setSelectedCampaign] = useState("");
  const [referrals, setReferrals] = useState<Referral[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [targetJobId, setTargetJobId] = useState("");
  const [budgetAmount, setBudgetAmount] = useState("");
  const [budgetCurrency, setBudgetCurrency] = useState("GBP");
  const [channelKey, setChannelKey] = useState("employee_referral");
  const [channelLabel, setChannelLabel] = useState("");
  const [channelSpend, setChannelSpend] = useState("");
  const [channelSpendCurrency, setChannelSpendCurrency] = useState("GBP");
  const [candidateId, setCandidateId] = useState("");
  const [applicationId, setApplicationId] = useState("");
  const [referrerName, setReferrerName] = useState("");
  const [referralNotes, setReferralNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  async function loadCampaigns(orgId: string) {
    if (!API_BASE || !orgId) return;
    const response = await apiFetch(`${API_BASE}/api/campaigns?organization_id=${encodeURIComponent(orgId)}`);
    const body = await response.json();
    if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Could not load campaigns.");
    const list = body as Campaign[];
    setCampaigns(list);
    if (!selectedCampaign && list.length) setSelectedCampaign(list[0].id);
  }

  async function loadReferrals(orgId: string, campaignId: string) {
    if (!orgId || !campaignId) return;
    const params = new URLSearchParams({ organization_id: orgId, campaign_id: campaignId });
    const response = await apiFetch(`${API_BASE}/api/referrals?${params.toString()}`);
    const body = await response.json();
    if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Could not load referrals.");
    setReferrals(body as Referral[]);
  }

  useEffect(() => {
    const orgId = getActiveOrganizationId();
    setOrganizationId(orgId);
    void loadCampaigns(orgId).catch((error) => setMessage(error instanceof Error ? error.message : "Could not load campaigns."));
  }, []);

  useEffect(() => {
    if (organizationId && selectedCampaign) {
      void loadReferrals(organizationId, selectedCampaign).catch((error) => setMessage(error instanceof Error ? error.message : "Could not load referrals."));
    }
  }, [organizationId, selectedCampaign]);

  async function createCampaign(event: FormEvent) {
    event.preventDefault();
    setLoading(true); setMessage("");
    try {
      const response = await apiFetch(`${API_BASE}/api/campaigns`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          organization_id: organizationId,
          name: name.trim(),
          description: description.trim() || null,
          ...(targetJobId.trim() ? { target_job_id: targetJobId.trim() } : {}),
          ...(budgetAmount ? { budget_amount: Number(budgetAmount), budget_currency: budgetCurrency } : {}),
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Could not create campaign.");
      setName(""); setDescription(""); setTargetJobId(""); setBudgetAmount("");
      setSelectedCampaign(body.id);
      await loadCampaigns(organizationId);
      setMessage("Campaign created.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not create campaign.");
    } finally {
      setLoading(false);
    }
  }

  async function changeCampaignStatus(campaign: Campaign, status: string) {
    if (status === campaign.status) return;
    const reason = window.prompt("Record the reason for this campaign status change:");
    if (!reason?.trim()) return;
    setLoading(true); setMessage("");
    try {
      const response = await apiFetch(`${API_BASE}/api/campaigns/${campaign.id}/status`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ organization_id: organizationId, status, reason: reason.trim() }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Could not update campaign.");
      await loadCampaigns(organizationId);
      setMessage("Campaign status updated with an audit reason.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not update campaign.");
    } finally {
      setLoading(false);
    }
  }

  async function createChannel(event: FormEvent) {
    event.preventDefault();
    if (!selectedCampaign) return;
    setLoading(true); setMessage("");
    try {
      const response = await apiFetch(`${API_BASE}/api/campaigns/${selectedCampaign}/channels`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          organization_id: organizationId,
          channel_key: channelKey,
          source_label: channelLabel.trim() || null,
          ...(channelSpend ? { spend_amount: Number(channelSpend), spend_currency: channelSpendCurrency } : {}),
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Could not add channel.");
      setChannelLabel(""); setChannelSpend("");
      setMessage("Campaign channel added.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not add channel.");
    } finally {
      setLoading(false);
    }
  }

  async function createReferral(event: FormEvent) {
    event.preventDefault();
    if (!selectedCampaign) return;
    setLoading(true); setMessage("");
    try {
      const response = await apiFetch(`${API_BASE}/api/referrals`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          organization_id: organizationId,
          campaign_id: selectedCampaign,
          ...(candidateId.trim() ? { candidate_id: candidateId.trim() } : {}),
          ...(applicationId.trim() ? { application_id: applicationId.trim() } : {}),
          ...(referrerName.trim() ? { referrer_name: referrerName.trim() } : {}),
          ...(referralNotes.trim() ? { notes: referralNotes.trim() } : {}),
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Could not create referral.");
      setCandidateId(""); setApplicationId(""); setReferrerName(""); setReferralNotes("");
      await loadReferrals(organizationId, selectedCampaign);
      await loadCampaigns(organizationId);
      setMessage("Referral recorded.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not create referral.");
    } finally {
      setLoading(false);
    }
  }

  async function correctStatus(referral: Referral, status: Referral["status"]) {
    const reason = window.prompt("Record the reason for this status change:");
    if (!reason?.trim()) return;
    setLoading(true); setMessage("");
    try {
      const response = await apiFetch(`${API_BASE}/api/referrals/${referral.id}/status`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ organization_id: organizationId, status, reason: reason.trim() }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Could not update referral.");
      await loadReferrals(organizationId, selectedCampaign);
      await loadCampaigns(organizationId);
      setMessage("Referral status updated with an audit reason.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not update referral.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Section 4 · Sourcing and attribution</p>
          <h1>Recruitment campaigns</h1>
          <p className="subtitle">Track sourcing channels, referrals and outcomes with organisation-scoped records and auditable status corrections.</p>
        </div>
      </header>
      {message && <div className="notice" role="status" style={{ marginBottom: 16 }}>{message}</div>}

      <section className="card" style={{ marginBottom: 20 }}>
        <div className="card-head"><span className="card-title">Create campaign</span></div>
        <form onSubmit={createCampaign}>
          <label>Campaign name<input required maxLength={160} value={name} onChange={(event) => setName(event.target.value)} placeholder="Graduate engineering hiring" /></label>
          <label>Description<textarea rows={2} maxLength={3000} value={description} onChange={(event) => setDescription(event.target.value)} /></label>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 12 }}>
            <label>Target job ID (optional)<input value={targetJobId} onChange={(event) => setTargetJobId(event.target.value)} placeholder="Job UUID" /></label>
            <label>Budget amount (optional)<input type="number" min="0" step="0.01" value={budgetAmount} onChange={(event) => setBudgetAmount(event.target.value)} /></label>
            <label>Budget currency<select value={budgetCurrency} onChange={(event) => setBudgetCurrency(event.target.value)}><option>GBP</option><option>USD</option><option>INR</option><option>AUD</option></select></label>
          </div>
          <button className="btn primary" disabled={loading || !organizationId}>{loading ? "Saving…" : "Create campaign"}</button>
        </form>
      </section>

      <section className="card" style={{ marginBottom: 20 }}>
        <div className="card-head"><span className="card-title">Campaign performance</span><span className="muted-small">{campaigns.length} campaigns</span></div>
        {campaigns.length === 0 ? <p className="muted-small">No campaigns created yet.</p> : (
          <div style={{ overflowX: "auto" }}><table className="table">
            <thead><tr><th>Campaign</th><th>Attributed candidates</th><th>Referrals</th><th>Qualified</th><th>Hired referrals</th><th>Qualified applications</th><th>Interview progress</th><th>Hired applications</th><th>Channel spend</th><th>Cost per hire</th></tr></thead>
            <tbody>{campaigns.map((campaign) => <tr key={campaign.id}>
              <td><button type="button" className="link" onClick={() => setSelectedCampaign(campaign.id)}>{campaign.name}</button><div><select aria-label={"Campaign status " + campaign.id} disabled={loading} value={campaign.status} onChange={(event) => void changeCampaignStatus(campaign, event.target.value)}><option value="draft">Draft</option><option value="scheduled">Scheduled</option><option value="active">Active</option><option value="paused">Paused</option><option value="completed">Completed</option><option value="cancelled">Cancelled</option></select></div></td>
              <td>{campaign.attributed_candidates ?? 0}</td><td>{campaign.referrals ?? 0}</td><td>{campaign.qualified_referrals ?? 0}</td><td>{campaign.hired_referrals ?? 0}</td>
              <td>{campaign.qualified_applications ?? 0}</td><td>{campaign.interview_progressed_applications ?? 0}</td><td>{campaign.hired_applications ?? 0}</td>
              <td>{campaign.channel_spend == null ? "—" : `${campaign.channel_spend_currency ?? ""} ${Number(campaign.channel_spend).toFixed(2)}`}</td>
              <td>{campaign.cost_per_hire == null ? "—" : `${campaign.channel_spend_currency ?? ""} ${Number(campaign.cost_per_hire).toFixed(2)}`}</td>
            </tr>)}</tbody>
          </table></div>
        )}
      </section>

      {selectedCampaign && (
        <>
          <section className="card" style={{ marginBottom: 20 }}>
            <div className="card-head"><span className="card-title">Add sourcing channel</span></div>
            <form onSubmit={createChannel}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 12 }}>
                <label>Channel<select value={channelKey} onChange={(event) => setChannelKey(event.target.value)}><option value="employee_referral">Employee referral</option><option value="careers_site">Careers site</option><option value="linkedin">LinkedIn</option><option value="job_board">Job board</option><option value="agency">Agency</option><option value="event">Event</option><option value="email">Email</option><option value="social">Social</option><option value="other">Other</option></select></label>
                <label>Source label (optional)<input value={channelLabel} onChange={(event) => setChannelLabel(event.target.value)} placeholder="University careers fair" /></label>
                <label>Recorded channel spend (optional)<input type="number" min="0" step="0.01" value={channelSpend} onChange={(event) => setChannelSpend(event.target.value)} /></label>
                <label>Spend currency<select value={channelSpendCurrency} onChange={(event) => setChannelSpendCurrency(event.target.value)}><option>GBP</option><option>USD</option><option>INR</option><option>AUD</option></select></label>
              </div>
              <button className="btn" disabled={loading}>Add channel</button>
            </form>
          </section>

          <section className="card" style={{ marginBottom: 20 }}>
            <div className="card-head"><span className="card-title">Record a referral</span></div>
            <form onSubmit={createReferral}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 12 }}>
                <label>Candidate ID (optional)<input value={candidateId} onChange={(event) => setCandidateId(event.target.value)} placeholder="Existing candidate UUID" /></label>
                <label>Application ID (optional)<input value={applicationId} onChange={(event) => setApplicationId(event.target.value)} placeholder="Application UUID for attribution metrics" /></label>
                <label>Referrer name (optional)<input value={referrerName} onChange={(event) => setReferrerName(event.target.value)} maxLength={160} /></label>
              </div>
              <label>Notes<textarea rows={2} maxLength={2000} value={referralNotes} onChange={(event) => setReferralNotes(event.target.value)} /></label>
              <button className="btn primary" disabled={loading}>Record referral</button>
            </form>
          </section>

          <section className="card">
            <div className="card-head"><span className="card-title">Campaign referrals</span><span className="muted-small">{referrals.length} shown</span></div>
            {referrals.length === 0 ? <p className="muted-small">No referrals recorded for this campaign.</p> : (
              <div style={{ overflowX: "auto" }}><table className="table">
                <thead><tr><th>Received</th><th>Referrer</th><th>Candidate ID</th><th>Status</th><th>Correct status</th></tr></thead>
                <tbody>{referrals.map((referral) => <tr key={referral.id}>
                  <td>{new Date(referral.received_at).toLocaleDateString()}</td><td>{referral.referrer_name || "Not specified"}</td><td>{referral.candidate_id || "Not linked"}</td><td>{referral.status}</td>
                  <td><select aria-label={"Correct referral status " + referral.id} disabled={loading} value={referral.status} onChange={(event) => void correctStatus(referral, event.target.value as Referral["status"])}><option value="received">Received</option><option value="reviewing">Reviewing</option><option value="qualified">Qualified</option><option value="interviewing">Interviewing</option><option value="hired">Hired</option><option value="declined">Declined</option><option value="withdrawn">Withdrawn</option></select></td>
                </tr>)}</tbody>
              </table></div>
            )}
          </section>
        </>
      )}
    </main>
  );
}
