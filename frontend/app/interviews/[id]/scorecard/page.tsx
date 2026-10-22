"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { getActiveOrganizationId } from "@/lib/organization";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";
const DEFAULT_ORG = process.env.NEXT_PUBLIC_ORGANIZATION_ID ?? "";

type Competency = {
  id: string; name: string; description: string;
  rating_guidance?: Record<string, string>; questions?: { id: string; question: string; evaluation_guidance?: string | null }[];
};
type TemplateResult = {
  application_id: string; interviewer_ids: string[];
  template: { template_id: string; kit_id: string; name: string; version_number: number; instructions?: string | null } | null;
  competencies: Competency[];
};
type ResponseDraft = { competency_id: string; rating: number; evidence: string; notes: string };
type Review = {
  assigned_interviewer_count: number; submitted_feedback_count: number;
  missing_interviewer_ids: string[];
  feedback: { response_id?: string | null; interviewer_id: string; competency_name?: string | null; rating?: number | null; evidence?: string | null; notes?: string | null; overall_summary?: string | null; strengths?: string | null; concerns?: string | null }[];
  decisions?: { id: string; reviewer_id: string; decision: string; rationale: string; evidence_snapshot: unknown[]; created_at: string }[];
  note: string;
};

const ratingLabels: Record<number, string> = {
  1: "1 · No evidence yet",
  2: "2 · Limited evidence",
  3: "3 · Meets requirement",
  4: "4 · Strong evidence",
  5: "5 · Exceptional evidence",
};

export default function InterviewScorecardPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<TemplateResult | null>(null);
  const [responses, setResponses] = useState<Record<string, ResponseDraft>>({});
  const [summary, setSummary] = useState("");
  const [strengths, setStrengths] = useState("");
  const [concerns, setConcerns] = useState("");
  const [review, setReview] = useState<Review | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [decisionValue, setDecisionValue] = useState("hold");
  const [decisionRationale, setDecisionRationale] = useState("");
  const [selectedEvidence, setSelectedEvidence] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  const loadReview = useCallback(async () => {
    const response = await apiFetch(API_BASE + "/api/interviews/" + id + "/scorecard-review");
    if (response.ok) setReview(await response.json());
  }, [id]);

  useEffect(() => {
    void (async () => {
      try {
        const [templateResponse, ownResponse] = await Promise.all([
          apiFetch(API_BASE + "/api/interviews/" + id + "/scorecard-template"),
          apiFetch(API_BASE + "/api/interviews/" + id + "/scorecards/me"),
        ]);
        if (!templateResponse.ok) throw new Error("Unable to load the scorecard template.");
        const templateData: TemplateResult = await templateResponse.json();
        setData(templateData);
        if (ownResponse.ok) {
          const own = await ownResponse.json();
          if (own) {
            setSummary(own.overall_summary ?? "");
            setStrengths(own.strengths ?? "");
            setConcerns(own.concerns ?? "");
            setSubmitted(own.status === "submitted");
            const saved: Record<string, ResponseDraft> = {};
            for (const response of own.responses ?? []) {
              saved[response.competency_id] = {
                competency_id: response.competency_id, rating: response.rating,
                evidence: response.evidence ?? "", notes: response.notes ?? "",
              };
            }
            setResponses(saved);
          }
        }
        await loadReview();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Unable to load this scorecard.");
      } finally {
        setLoading(false);
      }
    })();
  }, [id, loadReview]);

  function updateResponse(competencyId: string, field: keyof ResponseDraft, value: string | number) {
    setResponses((current) => ({
      ...current,
      [competencyId]: {
        competency_id: competencyId,
        rating: current[competencyId]?.rating ?? 3,
        evidence: current[competencyId]?.evidence ?? "",
        notes: current[competencyId]?.notes ?? "",
        [field]: value,
      },
    }));
  }

  async function save(submit: boolean) {
    if (!data?.template) return;
    setSaving(true); setMessage("");
    try {
      const payload = {
        template_id: data.template.template_id,
        overall_summary: summary || null,
        strengths: strengths || null,
        concerns: concerns || null,
        responses: data.competencies
          .filter((item) => responses[item.id])
          .map((item) => responses[item.id]),
      };
      const endpoint = API_BASE + "/api/interviews/" + id + "/scorecards" + (submit ? "/submit" : "");
      const response = await apiFetch(endpoint, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json().catch(() => null);
      if (!response.ok) throw new Error(result?.detail ?? "Unable to save scorecard.");
      if (submit) {
        setSubmitted(true);
        setMessage("Feedback submitted and locked. You can now review submitted assessments.");
        await loadReview();
      } else {
        setMessage("Draft saved. Other interviewers' feedback remains hidden until you submit your own.");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to save scorecard.");
    } finally {
      setSaving(false);
    }
  }


  async function saveDecision() {
    const organizationId = getActiveOrganizationId(DEFAULT_ORG);
    if (decisionRationale.trim().length < 20 || selectedEvidence.length === 0) {
      setMessage("Provide a rationale of at least 20 characters and select at least one evidence item.");
      return;
    }
    setSaving(true); setMessage("");
    try {
      const query = new URLSearchParams({ organization_id: organizationId });
      const response = await apiFetch(API_BASE + "/api/interviews/" + id + "/scorecard-decision?" + query, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision: decisionValue, rationale: decisionRationale, evidence_response_ids: selectedEvidence }),
      });
      const result = await response.json().catch(() => null);
      if (!response.ok) throw new Error(result?.detail ?? "Unable to record review decision. Only organisation owners/admins can do this.");
      setMessage("Review decision recorded with an immutable evidence snapshot.");
      setDecisionRationale(""); setSelectedEvidence([]);
      await loadReview();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to record review decision.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <main className="p-8"><p>Loading scorecard…</p></main>;
  if (!data) return <main className="p-8"><Link href={"/interviews/" + id}>← Interview details</Link><p className="mt-5">{message || "Unable to load scorecard."}</p></main>;
  if (!data.template) return (
    <main className="p-8 mx-auto max-w-3xl">
      <Link href={"/interviews/" + id}>← Interview details</Link>
      <h1 className="mt-6 text-2xl font-semibold">No published scorecard</h1>
      <p className="mt-2 text-gray-500">Ask an organisation admin to publish an interview kit that applies to this vacancy.</p>
      {message && <p className="notice mt-4">{message}</p>}
    </main>
  );

  return (
    <main className="p-8 mx-auto max-w-5xl">
      <Link href={"/interviews/" + id}>← Interview details</Link>
      <div className="mt-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold">{data.template.name}</h1>
          <p className="mt-2 text-sm text-gray-500">Version {data.template.version_number} · Structured interview feedback</p>
          {data.template.instructions && <p className="mt-3 max-w-3xl">{data.template.instructions}</p>}
        </div>
        {submitted && <span className="rounded-full border px-3 py-1 text-sm">Submitted · locked</span>}
      </div>
      {message && <div className="notice mt-5" role="status">{message}</div>}

      <div className="mt-6 rounded-xl border p-4 text-sm text-gray-600">
        Rate observable evidence against the role requirements. Record specific examples, not impressions. Scores support human review and do not make the hiring decision.
      </div>

      <section className="mt-6 space-y-4">
        {data.competencies.map((item, index) => {
          const response = responses[item.id];
          return (
            <article className="card" key={item.id}>
              <h2 className="text-lg font-semibold">{index + 1}. {item.name}</h2>
              <p className="mt-2 text-sm text-gray-600">{item.description}</p>
              {item.questions?.map((question) => (
                <div className="mt-3 rounded-lg bg-gray-50 p-3 text-sm" key={question.id}>
                  <p className="font-medium">{question.question}</p>
                  {question.evaluation_guidance && <p className="mt-1 text-gray-600">{question.evaluation_guidance}</p>}
                </div>
              ))}
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <label className="block text-sm">Rating
                  <select className="input mt-1 w-full" value={response?.rating ?? 3} disabled={submitted} onChange={(e) => updateResponse(item.id, "rating", Number(e.target.value))}>
                    {[1, 2, 3, 4, 5].map((rating) => <option value={rating} key={rating}>{ratingLabels[rating]}</option>)}
                  </select>
                </label>
                <label className="block text-sm">Evidence observed (required to submit)
                  <textarea className="input mt-1 w-full" rows={3} maxLength={4000} value={response?.evidence ?? ""} disabled={submitted} onChange={(e) => updateResponse(item.id, "evidence", e.target.value)} placeholder="What did the candidate say or demonstrate that supports this rating?" />
                </label>
                <label className="block text-sm md:col-span-2">Additional notes
                  <textarea className="input mt-1 w-full" rows={2} maxLength={4000} value={response?.notes ?? ""} disabled={submitted} onChange={(e) => updateResponse(item.id, "notes", e.target.value)} />
                </label>
              </div>
            </article>
          );
        })}
      </section>

      <section className="card mt-6 space-y-4">
        <h2 className="text-lg font-semibold">Overall evidence summary</h2>
        <label className="block text-sm">Summary
          <textarea className="input mt-1 w-full" rows={3} maxLength={4000} value={summary} disabled={submitted} onChange={(e) => setSummary(e.target.value)} placeholder="Summarise evidence relevant to the role." />
        </label>
        <div className="grid gap-4 md:grid-cols-2">
          <label className="block text-sm">Strengths evidenced
            <textarea className="input mt-1 w-full" rows={3} maxLength={4000} value={strengths} disabled={submitted} onChange={(e) => setStrengths(e.target.value)} />
          </label>
          <label className="block text-sm">Concerns or gaps to clarify
            <textarea className="input mt-1 w-full" rows={3} maxLength={4000} value={concerns} disabled={submitted} onChange={(e) => setConcerns(e.target.value)} />
          </label>
        </div>
        {!submitted && <div className="flex flex-wrap gap-3">
          <button className="btn" disabled={saving} onClick={() => void save(false)}>{saving ? "Saving…" : "Save draft"}</button>
          <button className="btn primary" disabled={saving || data.competencies.some((item) => !responses[item.id]?.evidence?.trim())} onClick={() => void save(true)}>Submit final feedback</button>
        </div>}
      </section>

      {review && (submitted || review.submitted_feedback_count > 0) && (
        <section className="mt-10">
          <h2 className="text-xl font-semibold">Consolidated review</h2>
          <p className="mt-2 text-sm text-gray-600">{review.submitted_feedback_count} of {review.assigned_interviewer_count} assigned interviewers submitted feedback.</p>
          {review.missing_interviewer_ids.length > 0 && <div className="notice mt-3">Missing assessments: {review.missing_interviewer_ids.join(", ")}</div>}
          <p className="mt-3 text-sm text-gray-600">{review.note}</p>
          <div className="mt-4 space-y-3">
            {review.feedback.map((entry, index) => (
              <article className="card" key={entry.interviewer_id + "-" + (entry.competency_name ?? "summary") + "-" + index}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="font-semibold">{entry.competency_name || "Overall feedback"}</h3>
                  <span className="text-sm">Interviewer {entry.interviewer_id.slice(0, 8)}{entry.rating ? " · Rating " + entry.rating + "/5" : ""}</span>
                </div>
                {entry.evidence && <p className="mt-2 text-sm">{entry.evidence}</p>}
                {entry.overall_summary && <p className="mt-2 text-sm">{entry.overall_summary}</p>}
                {entry.strengths && <p className="mt-2 text-sm"><strong>Strengths:</strong> {entry.strengths}</p>}
                {entry.concerns && <p className="mt-2 text-sm"><strong>Concerns:</strong> {entry.concerns}</p>}
                {entry.response_id && <label className="mt-3 flex items-center gap-2 text-sm"><input type="checkbox" checked={selectedEvidence.includes(entry.response_id)} onChange={(event) => setSelectedEvidence((current) => event.target.checked ? [...current, entry.response_id!] : current.filter((value) => value !== entry.response_id))} />Use this evidence in a formal review decision</label>}
              </article>
            ))}
          </div>
          {review.decisions && review.decisions.length > 0 && <div className="mt-6 space-y-3"><h3 className="font-semibold">Recorded review decisions</h3>{review.decisions.map((item) => <article className="card" key={item.id}><p className="font-semibold">{item.decision.replaceAll("_", " ")}</p><p className="mt-2 text-sm">{item.rationale}</p><p className="mt-2 text-xs text-gray-500">Reviewer {item.reviewer_id.slice(0, 8)} · {new Date(item.created_at).toLocaleString()} · {item.evidence_snapshot.length} evidence items captured</p></article>)}</div>}
          <section className="card mt-6 space-y-4">
            <h3 className="text-lg font-semibold">Record a human review decision</h3>
            <p className="text-sm text-gray-600">Organisation owners/admins only. Every assigned interviewer must submit first, and the decision must cite specific submitted evidence.</p>
            <label className="block text-sm">Decision
              <select className="input mt-1 w-full" value={decisionValue} onChange={(event) => setDecisionValue(event.target.value)}><option value="proceed">Proceed</option><option value="decline">Decline</option><option value="additional_interview">Additional interview</option><option value="hold">Hold</option></select>
            </label>
            <label className="block text-sm">Decision rationale
              <textarea className="input mt-1 w-full" rows={3} minLength={20} maxLength={4000} value={decisionRationale} onChange={(event) => setDecisionRationale(event.target.value)} placeholder="Explain how the cited evidence supports this decision." />
            </label>
            <button className="btn primary" disabled={saving || selectedEvidence.length === 0 || decisionRationale.trim().length < 20} onClick={() => void saveDecision()}>Record evidence-linked decision</button>
          </section>
        </section>
      )}
    </main>
  );
}
