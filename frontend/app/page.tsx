"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch, API_BASE } from "@/lib/api";

type DashboardData = { open_requisitions:number; active_candidates:number; active_clients:number; scheduled_interviews:number; active_offers:number; active_placements:number; pipeline:Record<string,number>; jobs:Array<{id:string;title:string;client:string;status:string;applicants:number}>; activity:Array<{action:string;entity_type:string;entity_id:string;metadata:Record<string,unknown>|null;created_at:string}> };



const nav = ["Dashboard", "Jobs", "Candidates", "Submissions", "Interviews", "Clients", "Vendors", "Talent Bench", "Onboarding", "Placements", "Leads", "Reports"];

export default function Dashboard() {
  const [data,setData]=useState<DashboardData|null>(null);
  useEffect(()=>{const org=typeof window!=="undefined"?window.localStorage.getItem("talentos_active_org")||process.env.NEXT_PUBLIC_ORGANIZATION_ID:""; if(!API_BASE||!org)return; apiFetch(API_BASE+"/api/dashboard?organization_id="+encodeURIComponent(org)).then(r=>r.ok?r.json():null).then(setData).catch(()=>{});},[]);
  return (
    <div className="shell">
      <aside className="sidebar">
        <Link href="/" className="brand">Talent<span>OS</span></Link>
        <div className="nav-label">Workspace</div>
        {nav.map((item, i) => item === "Jobs"
          ? <Link key={item} href="/jobs" className="nav-item"><span>▣</span><span>{item}</span></Link>
          : item === "Candidates"
          ? <Link key={item} href="/candidates" className="nav-item"><span>♙</span><span>{item}</span></Link>
          : item === "Submissions"
          ? <Link key={item} href="/submissions" className="nav-item"><span>↗</span><span>{item}</span></Link>
          : <div key={item} className={i === 0 ? "nav-item active" : "nav-item"}><span>{["⌂","▣","♙","↗","◷","□","◇","♧","✓","◈","◌","▤"][i]}</span><span>{item}</span></div>
        )}
        <div className="nav-label">Administration</div>
        <div className="nav-item"><span>⚙</span><span>Settings</span></div>
        <div className="nav-item"><span>?</span><span>Help & support</span></div>
      </aside>

      <main className="main">
        <header className="topbar">
          <input className="search" placeholder="Search candidates, jobs, clients..." aria-label="Global search" />
          <div className="profile"><span>Acme Recruitment</span><div className="avatar">VG</div></div>
        </header>

        <section className="content">
          <div className="header-row">
            <div><div className="eyebrow">Recruitment operations</div><h1>Good afternoon</h1><p className="subtitle">Here’s what is happening across your hiring pipeline.</p></div>
            <div className="actions"><Link href="/jobs" className="btn">Manage jobs</Link><Link href="/jobs" className="btn primary">+ New requisition</Link></div>
          </div>

          <div className="metrics">
            <div className="card"><div className="metric-title">Open requisitions</div><div className="metric-value">{data?.open_requisitions ?? "—"}</div><div className="metric-foot">↑ 8% this month</div></div>
            <div className="card"><Link href="/candidates" style={{display:"block"}}><div className="metric-title">Active candidates</div><div className="metric-value">{data?.active_candidates ?? "—"}</div></Link><div className="metric-foot">↑ 12% this month</div></div>
            <div className="card"><div className="metric-title">Interviews this week</div><div className="metric-value">{data ? (data.scheduled_interviews ?? 0) : "—"}</div><div className="metric-foot">↑ 5 from last week</div></div>
            <div className="card"><div className="metric-title">Placements this month</div><div className="metric-value">{data ? (data.active_placements ?? 0) : "—"}</div><div className="metric-foot">↑ 20% this month</div></div>
          </div>

          <div className="card" style={{ marginBottom: 18 }}>
            <div className="card-head"><span className="card-title">Recruitment pipeline</span><Link href="/submissions" className="link">View pipeline →</Link></div>
            <div className="pipeline">{[["New applicants","new"],["Screening","screening"],["Submitted","submitted"],["Interview","interview"],["Offer","offer"]].map(([label,key]) => <div className="stage" key={label}><strong>{data?.pipeline?.[key] ?? "—"}</strong><span>{label}</span></div>)}</div>
          </div>

          <div className="grid">
            <div className="card">
              <div className="card-head"><span className="card-title">Active requisitions</span><Link href="/jobs" className="link">View all →</Link></div>
              <table className="table"><thead><tr><th>Position</th><th>Client</th><th>Applicants</th><th>Status</th></tr></thead><tbody>{(data?.jobs ?? []).map(j => <tr key={j.id}><td><strong>{j.title}</strong></td><td>{j.client}</td><td>{j.applicants}</td><td><span className={j.status === "open" ? "badge green" : "badge amber"}>{j.status}</span></td></tr>)}</tbody></table>
            </div>
            <div className="card">
              <div className="card-head"><span className="card-title">Recent activity</span><span className="link">View activity →</span></div>
              <div className="activity">{(data?.activity ?? []).map((item, i) => <div className="activity-row" key={`${item.entity_id}-${item.created_at}-${i}`}><div className="dot"/><div className="activity-text"><strong>{item.action}</strong><div className="activity-time">{new Date(item.created_at).toLocaleString()}</div></div></div>)}</div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
