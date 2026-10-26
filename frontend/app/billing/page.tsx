"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, API_BASE } from "@/lib/api";
import { getActiveOrganizationId } from "@/lib/organization";

type Plan = {
  id: string;
  plan_key: string;
  display_name: string;
  description?: string | null;
  entitlements: Record<string, boolean | number | null>;
};

type Subscription = {
  id: string;
  status: string;
  plan_name: string;
  current_period_end?: string | null;
  cancel_at_period_end: boolean;
} | null;

export default function BillingPage() {
  const [organizationId, setOrganizationId] = useState("");
  const [plans, setPlans] = useState<Plan[]>([]);
  const [subscription, setSubscription] = useState<Subscription>(null);
  const [loading, setLoading] = useState(true);
  const [busyPlan, setBusyPlan] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async (orgId: string) => {
    if (!API_BASE) {
      setMessage("The billing API is not configured for this environment.");
      setLoading(false);
      return;
    }
    try {
      const [plansResponse, subscriptionResponse] = await Promise.all([
        apiFetch(API_BASE + "/api/billing/plans"),
        apiFetch(API_BASE + "/api/billing/subscription?organization_id=" + encodeURIComponent(orgId)),
      ]);
      if (!plansResponse.ok || !subscriptionResponse.ok) {
        throw new Error("Unable to load billing information. Check your workspace permissions and API configuration.");
      }
      const plansBody = await plansResponse.json();
      const subscriptionBody = await subscriptionResponse.json();
      setPlans(plansBody.plans ?? []);
      setSubscription(subscriptionBody.subscription ?? null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load billing information.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const orgId = getActiveOrganizationId();
    setOrganizationId(orgId);
    if (!orgId) {
      setMessage("Select or create a recruitment workspace before managing billing.");
      setLoading(false);
      return;
    }
    void load(orgId);

    const params = new URLSearchParams(window.location.search);
    if (params.get("checkout") === "success") {
      setMessage("Checkout returned successfully. Your subscription status will update after Stripe confirms it.");
    } else if (params.get("checkout") === "cancelled") {
      // A cancelled Checkout Session cannot be resumed; allow a fresh attempt.
      for (let index = sessionStorage.length - 1; index >= 0; index -= 1) {
        const key = sessionStorage.key(index);
        if (key?.startsWith("aqerith:checkout:")) sessionStorage.removeItem(key);
      }
      setMessage("Checkout was cancelled. No subscription change was confirmed.");
    }
  }, [load]);

  async function startCheckout(planId: string) {
    setBusyPlan(planId);
    setMessage("");
    try {
      // Keep one idempotency key per organisation/plan attempt so retries after
      // a timeout or reload reuse the same Stripe Checkout Session.
      const storageKey = `aqerith:checkout:${organizationId}:${planId}`;
      let idempotencyKey = sessionStorage.getItem(storageKey);
      if (!idempotencyKey) {
        idempotencyKey = crypto.randomUUID();
        sessionStorage.setItem(storageKey, idempotencyKey);
      }
      const response = await apiFetch(API_BASE + "/api/billing/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ organization_id: organizationId, plan_id: planId, idempotency_key: idempotencyKey }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || "Unable to start checkout.");
      if (!body.checkout_url) throw new Error("The billing provider did not return a checkout URL.");
      window.location.assign(body.checkout_url);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to start checkout.");
    } finally {
      setBusyPlan("");
    }
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
        <Link href="/billing" className="nav-item active" aria-current="page">Plans & billing</Link>
      </aside>
      <main className="main">
        <header className="topbar">
          <div><strong>Plans & billing</strong><div className="muted-small">Manage your organisation subscription</div></div>
          <Link href="/" className="btn">Back to workspace</Link>
        </header>
        <section className="content">
          <div className="eyebrow">Commercial settings</div>
          <h1>Plans & billing</h1>
          <p className="subtitle">Subscription status and plan access are confirmed by AQERITH's server, not by browser state.</p>
          {message && <div className="notice" role="status">{message}</div>}
          {loading ? <div className="card">Loading billing information…</div> : (
            <>
              <section className="card" aria-labelledby="current-plan-heading">
                <div className="card-head">
                  <div>
                    <div className="metric-title">Current subscription</div>
                    <h2 id="current-plan-heading" className="card-title">{subscription?.plan_name ?? "No active subscription"}</h2>
                  </div>
                  {subscription && <span className={"badge " + (["active", "trialing"].includes(subscription.status) ? "green" : "amber")}>{subscription.status.replaceAll("_", " ")}</span>}
                </div>
                {subscription ? (
                  <p className="muted-small">
                    {subscription.cancel_at_period_end ? "Cancellation is scheduled for the end of the current period." : "Subscription details are synchronised from the billing provider."}
                    {subscription.current_period_end ? " Current period ends " + new Date(subscription.current_period_end).toLocaleDateString() + "." : ""}
                  </p>
                ) : <p className="muted-small">Choose a plan below to begin a subscription. Pricing must be configured by the platform administrator.</p>}
              </section>

              <div className="header-row" style={{ marginTop: 28, marginBottom: 14 }}>
                <div><h2>Available plans</h2><p className="muted-small">Features shown here come from the server plan catalogue.</p></div>
              </div>
              {plans.length === 0 ? <div className="card">No active plans are configured yet.</div> : (
                <div className="metrics" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))" }}>
                  {plans.map((plan) => (
                    <article className="card" key={plan.id}>
                      <div className="eyebrow">{plan.plan_key}</div>
                      <h2 className="card-title" style={{ margin: "10px 0" }}>{plan.display_name}</h2>
                      <p className="muted-small">{plan.description || "A plan for your recruitment workspace."}</p>
                      <div className="feature-line" style={{ margin: "16px 0" }} />
                      <ul style={{ paddingLeft: 18, lineHeight: 1.8, fontSize: 13 }}>
                        {Object.entries(plan.entitlements).map(([key, value]) => (
                          <li key={key}>{key.replaceAll("_", " ")}: {value === null ? "Unlimited" : value === true ? "Included" : value === false ? "Not included" : value}</li>
                        ))}
                      </ul>
                      <button className="btn primary" disabled={Boolean(busyPlan) || Boolean(subscription && ["active", "trialing", "incomplete", "past_due", "paused", "unpaid"].includes(subscription.status))} onClick={() => void startCheckout(plan.id)}>
                        {busyPlan === plan.id ? "Starting checkout…" : "Choose plan"}
                      </button>
                    </article>
                  ))}
                </div>
              )}
            </>
          )}
        </section>
      </main>
    </div>
  );
}
