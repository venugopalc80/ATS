"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { getActiveOrganizationId } from "@/lib/organization";

type Workflow = { id: string; name: string; description?: string | null; status: string; draft_definition?: { trigger_event?: string }; updated_at: string };
type Run = { id: string; event_name: string; status: string; error_message?: string | null; created_at: string };
const API = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";
const EVENTS = ["application.created", "application.stage_changed", "interview.scheduled", "interview.feedback_overdue", "offer.approved"];
const ACTIONS = [
  ["assign_vacancy_recruiter", "Assign to vacancy recruiter"],
  ["create_interview_reminder", "Create interview reminder"],
  ["notify_interviewer_feedback_overdue", "Notify interviewer about overdue feedback"],
  ["prepare_offer_document_for_review", "Prepare offer for authorised review"],
  ["send_approved_template", "Send an approved template message"],
  ["request_human_approval", "Request human approval"],
];

export default function WorkflowsPage() {
  const [org, setOrg] = useState("");
  const [items, setItems] = useState<Workflow[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [selected, setSelected] = useState("");
  const [name, setName] = useState("Interview feedback reminder");
  const [description, setDescription] = useState("");
  const [eventName, setEventName] = useState("interview.feedback_overdue");
  const [action, setAction] = useState("notify_interviewer_feedback_overdue");
  const [approval, setApproval] = useState(false);
  const [preview, setPreview] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (organization: string) => {
    if (!organization) return;
    const query = "organization_id=" + encodeURIComponent(organization);
    const [a, b] = await Promise.all([
      apiFetch(API + "/api/workflows?" + query),
      apiFetch(API + "/api/workflows/runs?" + query + "&limit=20"),
    ]);
    if (!a.ok || !b.ok) throw new Error("Could not load workflows. Check permissions and apply the workflow migration.");
    const rows = await a.json() as Workflow[];
    setItems(rows);
    setRuns(await b.json() as Run[]);
    if (!selected && rows.length) setSelected(rows[0].id);
  }, [selected]);

  useEffect(() => {
    const organization = getActiveOrganizationId() ?? process.env.NEXT_PUBLIC_ORGANIZATION_ID ?? "";
    setOrg(organization);
    if (organization) load(organization).catch((error: Error) => setNotice(error.message));
  }, [load]);

  const selectedWorkflow = items.find((item) => item.id === selected);
  const payload = () => ({
    name: name.trim(),
    description: description.trim() || null,
    trigger_event: eventName,
    conditions: [],
    steps: [{
      key: "step-1",
      action,
      conditions: [],
      requires_approval: approval || action === "prepare_offer_document_for_review" || action === "send_approved_template",
      config: {},
    }],
  });

  async function saveDraft() {
    if (!org || !name.trim()) return;
    setBusy(true); setNotice(""); setPreview(null);
    try {
      const response = await apiFetch(API + "/api/workflows?organization_id=" + encodeURIComponent(org), {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload()),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail ?? "Could not save draft.");
      setSelected(result.id); setNotice("Draft saved. Preview before publishing.");
      await load(org);
    } catch (error) { setNotice(error instanceof Error ? error.message : "Could not save draft."); }
    finally { setBusy(false); }
  }

  async function testPreview() {
    if (!selected) { setNotice("Save a draft first."); return; }
    setBusy(true); setNotice("");
    try {
      const response = await apiFetch(API + "/api/workflows/" + selected + "/preview?organization_id=" + encodeURIComponent(org), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ event_name: eventName, event_payload: { interview: { status: "scheduled" } } }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail ?? "Preview failed.");
      setPreview(result); setNotice("Preview completed without side effects.");
    } catch (error) { setNotice(error instanceof Error ? error.message : "Preview failed."); }
    finally { setBusy(false); }
  }

  async function changeStatus(operation: "publish" | "disable") {
    if (!selected) return;
    setBusy(true); setNotice("");
    try {
      const response = await apiFetch(API + "/api/workflows/" + selected + "/" + operation + "?organization_id=" + encodeURIComponent(org), { method: "POST" });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail ?? "Workflow update failed.");
      setNotice(operation === "publish" ? "Version published. Event execution is not connected yet." : "Workflow disabled.");
      await load(org);
    } catch (error) { setNotice(error instanceof Error ? error.message : "Workflow update failed."); }
    finally { setBusy(false); }
  }

  return <main className="page-shell">
    <header className="page-header"><div><p className="eyebrow">AUTOMATION</p><h1>Recruitment workflows</h1><p className="muted">Draft, validate and publish repeatable recruitment operations with human approval boundaries.</p></div></header>
    {notice && <div className="notice" role="status">{notice}</div>}
    {!org && <div className="notice" role="alert">Select an organisation to manage workflows.</div>}
    <section className="panel">
      <div className="panel-heading"><div><h2>Workflow builder</h2><p className="muted">Version one uses a bounded linear sequence of steps.</p></div></div>
      <div className="form-grid">
        <label>Workflow name<input value={name} maxLength={120} onChange={(e) => setName(e.target.value)} /></label>
        <label>Trigger event<select value={eventName} onChange={(e) => setEventName(e.target.value)}>{EVENTS.map((event) => <option key={event} value={event}>{event}</option>)}</select></label>
        <label className="full-width">Description<input value={description} maxLength={2000} onChange={(e) => setDescription(e.target.value)} placeholder="What should this workflow do?" /></label>
        <label>Action<select value={action} onChange={(e) => setAction(e.target.value)}>{ACTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="checkbox-label"><input type="checkbox" checked={approval || action === "prepare_offer_document_for_review" || action === "send_approved_template"} disabled={action === "prepare_offer_document_for_review" || action === "send_approved_template"} onChange={(e) => setApproval(e.target.checked)} /> Require human approval</label>
      </div>
      <div className="button-row">
        <button disabled={busy || !org || !name.trim()} onClick={saveDraft}>Save draft</button>
        <button className="secondary" disabled={busy || !selected} onClick={testPreview}>Test preview</button>
        <button disabled={busy || !selected || selectedWorkflow?.status === "disabled"} onClick={() => changeStatus("publish")}>Publish version</button>
        <button className="danger" disabled={busy || !selected || selectedWorkflow?.status === "disabled"} onClick={() => changeStatus("disable")}>Disable</button>
      </div>
      {preview && <pre className="workflow-preview">{JSON.stringify(preview, null, 2)}</pre>}
    </section>
    <section className="panel"><div className="panel-heading"><div><h2>Saved workflows</h2><p className="muted">Select a workflow to inspect its current definition.</p></div></div>
      {items.length === 0 ? <p className="muted">No workflows yet.</p> : <div className="table-wrap"><table><thead><tr><th>Name</th><th>Trigger</th><th>Status</th><th>Updated</th></tr></thead><tbody>{items.map((item) => <tr key={item.id} className={selected === item.id ? "selected-row" : ""} onClick={() => { setSelected(item.id); setName(item.name); setDescription(item.description ?? ""); if (item.draft_definition?.trigger_event) setEventName(item.draft_definition.trigger_event); }}><td><strong>{item.name}</strong><small>{item.id}</small></td><td>{item.draft_definition?.trigger_event ?? "Published version"}</td><td><span className="status-pill">{item.status}</span></td><td>{new Date(item.updated_at).toLocaleString()}</td></tr>)}</tbody></table></div>}
    </section>
    <section className="panel"><div className="panel-heading"><div><h2>Execution history</h2><p className="muted">Run records will appear when event dispatch and worker execution are connected.</p></div></div>
      {runs.length === 0 ? <p className="muted">No workflow runs recorded.</p> : <div className="table-wrap"><table><thead><tr><th>Event</th><th>Status</th><th>Created</th><th>Details</th></tr></thead><tbody>{runs.map((run) => <tr key={run.id}><td>{run.event_name}</td><td><span className="status-pill">{run.status}</span></td><td>{new Date(run.created_at).toLocaleString()}</td><td>{run.error_message ?? run.id}</td></tr>)}</tbody></table></div>}
    </section>
  </main>;
}
