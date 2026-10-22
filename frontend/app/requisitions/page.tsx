'use client';

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { getActiveOrganizationId } from "@/lib/organization";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
const FALLBACK_ORG = process.env.NEXT_PUBLIC_ORGANIZATION_ID ?? "";
type Req = { id:string; organization_id:string; requisition_code:string; title:string; department?:string|null; headcount:number; justification:string; location?:string|null; country_code?:string|null; employment_type?:string|null; work_mode?:string|null; salary_min?:number|string|null; salary_max?:number|string|null; salary_currency?:string|null; required_skills?:string[]|null; recruiter_id?:string|null; hiring_manager_id?:string|null; status:string; rejection_reason?:string|null; job_id?:string|null; updated_at:string };
type Assignee = { user_id:string; full_name?:string|null; email?:string|null; role:string };
type FormState = { title:string; department:string; justification:string; headcount:string; location:string; country_code:string; employment_type:string; work_mode:string; salary_min:string; salary_max:string; salary_currency:string; required_skills:string; recruiter_id:string; hiring_manager_id:string };
const initial:FormState = { title:"",department:"",justification:"",headcount:"1",location:"",country_code:"GB",employment_type:"Permanent",work_mode:"Hybrid",salary_min:"",salary_max:"",salary_currency:"GBP",required_skills:"",recruiter_id:"",hiring_manager_id:"" };
const labels:Record<string,string> = { draft:"Draft",pending_approval:"Awaiting approval",approved:"Approved",rejected:"Rejected",converted:"Converted to job",cancelled:"Cancelled" };

export default function RequisitionsPage() {
 const [rows,setRows]=useState<Req[]>([]);
 const [assignees,setAssignees]=useState<Assignee[]>([]);
 const [form,setForm]=useState<FormState>(initial);
 const [showForm,setShowForm]=useState(false);
 const [editingId,setEditingId]=useState<string|null>(null);
 const [page,setPage]=useState(1);
 const [sortBy,setSortBy]=useState<"title"|"department"|"location"|"headcount"|"status"|"updated_at">("updated_at");
 const [sortDirection,setSortDirection]=useState<"asc"|"desc">("desc");
 const [loading,setLoading]=useState(true);
 const [saving,setSaving]=useState(false);
 const [busyId,setBusyId]=useState<string|null>(null);
 const [filter,setFilter]=useState("all");
 const [search,setSearch]=useState("");
 const [message,setMessage]=useState("");
 const load=useCallback(async()=>{
  const org=getActiveOrganizationId(FALLBACK_ORG);
  if(!API_BASE||!org){setMessage("Connect the API and select an organisation to manage requisitions.");setLoading(false);return;}
  setLoading(true);
  try{
   const params=new URLSearchParams({organization_id:org,limit:"100"});
   if(filter!=="all")params.set("status",filter);
   if(search.trim())params.set("search",search.trim());
   const response=await apiFetch(API_BASE+"/api/requisitions?"+params.toString());
   if(!response.ok)throw new Error((await response.json().catch(()=>null))?.detail||"Unable to load requisitions ("+response.status+")");
   setRows(await response.json());
   const teamResponse=await apiFetch(API_BASE+"/api/requisitions/assignees?organization_id="+encodeURIComponent(org));
   if(teamResponse.ok)setAssignees(await teamResponse.json());
   setMessage("");
  }catch(e){setMessage(e instanceof Error?e.message:"Unable to load requisitions.");}
  finally{setLoading(false);}
 },[filter,search]);
 useEffect(()=>{setPage(1);void load();},[load]);
 function change<K extends keyof FormState>(key:K,value:FormState[K]){setForm(old=>({...old,[key]:value}));}
 function startEdit(row:Req){
  setEditingId(row.id);setShowForm(true);setMessage("");
  setForm({title:row.title,department:row.department||"",justification:row.justification||"",headcount:String(row.headcount||1),location:row.location||"",country_code:row.country_code||"GB",employment_type:row.employment_type||"Permanent",work_mode:row.work_mode||"Hybrid",salary_min:row.salary_min==null?"":String(row.salary_min),salary_max:row.salary_max==null?"":String(row.salary_max),salary_currency:row.salary_currency||"GBP",required_skills:(row.required_skills||[]).join(", "),recruiter_id:row.recruiter_id||"",hiring_manager_id:row.hiring_manager_id||""});
 }
 async function create(event:FormEvent<HTMLFormElement>){
  event.preventDefault();const org=getActiveOrganizationId(FALLBACK_ORG);
  if(!API_BASE||!org){setMessage("Select an organisation before creating a requisition.");return;}
  if(form.salary_min&&form.salary_max&&Number(form.salary_max)<Number(form.salary_min)){setMessage("Maximum salary must be greater than or equal to minimum salary.");return;}
  setSaving(true);setMessage("");
  try{
   const payload={organization_id:org,title:form.title.trim(),department:form.department.trim()||null,justification:form.justification.trim(),headcount:Number(form.headcount),location:form.location.trim()||null,country_code:form.country_code,employment_type:form.employment_type,work_mode:form.work_mode,salary_min:form.salary_min?Number(form.salary_min):null,salary_max:form.salary_max?Number(form.salary_max):null,salary_currency:form.salary_currency,required_skills:form.required_skills.split(",").map(x=>x.trim()).filter(Boolean),recruiter_id:form.recruiter_id||null,hiring_manager_id:form.hiring_manager_id||null};
   const response=await apiFetch(API_BASE+"/api/requisitions"+(editingId?"/"+editingId:""),{method:editingId?"PATCH":"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
   if(!response.ok)throw new Error((await response.json().catch(()=>null))?.detail||"Unable to save draft.");
   setForm(initial);setShowForm(false);setEditingId(null);setMessage(editingId?"Draft requisition updated.":"Draft requisition saved.");await load();
  }catch(e){setMessage(e instanceof Error?e.message:"Unable to save draft.");}finally{setSaving(false);}
 }
 async function act(row:Req,action:"submit"|"approve"|"reject"|"convert-to-job"){
  if(!API_BASE)return;setBusyId(row.id);setMessage("");
  try{
   let body:string|undefined;
   if(action==="approve")body=JSON.stringify({comment:window.prompt("Optional approval comment")||null});
   if(action==="reject"){const reason=window.prompt("Enter a rejection reason");if(!reason?.trim())return;body=JSON.stringify({reason:reason.trim()});}
   const response=await apiFetch(API_BASE+"/api/requisitions/"+row.id+"/"+action,{method:"POST",headers:{"Content-Type":"application/json"},body});
   if(!response.ok)throw new Error((await response.json().catch(()=>null))?.detail||"Action failed ("+response.status+")");
   const result=await response.json().catch(()=>null);
   setMessage(action==="convert-to-job"?"Job created: "+(result?.job?.title||row.title)+". It remains a draft until opened.":"Requisition "+action.replaceAll("-"," ")+" completed.");
   await load();
  }catch(e){setMessage(e instanceof Error?e.message:"Action failed.");}finally{setBusyId(null);}
 }
 const count=rows.length,pending=rows.filter(r=>r.status==="pending_approval").length,drafts=rows.filter(r=>r.status==="draft"||r.status==="rejected").length,approved=rows.filter(r=>r.status==="approved").length;
 const sortedRows=[...rows].sort((a,b)=>{const av=a[sortBy]??"",bv=b[sortBy]??"";const result=sortBy==="headcount"?Number(av)-Number(bv):sortBy==="updated_at"?new Date(String(av)).getTime()-new Date(String(bv)).getTime():String(av).localeCompare(String(bv),undefined,{numeric:true,sensitivity:"base"});return sortDirection==="asc"?result:-result;});
 const pageSize=10,totalPages=Math.max(1,Math.ceil(sortedRows.length/pageSize));
 const visibleRows=sortedRows.slice((page-1)*pageSize,page*pageSize);
 function sort(column:typeof sortBy){if(sortBy===column)setSortDirection(v=>v==="asc"?"desc":"asc");else{setSortBy(column);setSortDirection(column==="updated_at"?"desc":"asc");}setPage(1);}
 return <div className="shell">
  <aside className="sidebar"><Link href="/dashboard" className="brand">AQERITH</Link><div className="nav-label">Workspace</div>
   <Link href="/dashboard" className="nav-item"><span>⌂</span><span>Dashboard</span></Link>
   <Link href="/jobs" className="nav-item"><span>▣</span><span>Jobs</span></Link>
   <Link href="/requisitions" className="nav-item active" aria-current="page"><span>✓</span><span>Requisitions</span></Link>
   <Link href="/candidates" className="nav-item"><span>♙</span><span>Candidates</span></Link><Link href="/submissions" className="nav-item"><span>↗</span><span>Submissions</span></Link>
   <Link href="/interviews" className="nav-item"><span>◷</span><span>Interviews</span></Link><Link href="/clients" className="nav-item"><span>□</span><span>Clients</span></Link>
   <Link href="/onboarding" className="nav-item"><span>✓</span><span>Onboarding</span></Link><Link href="/placements" className="nav-item"><span>◈</span><span>Placements</span></Link>
  </aside>
  <main className="main"><header className="topbar"><input className="search" placeholder="Search requisitions..." value={search} onChange={e=>setSearch(e.target.value)}/><div className="profile"><span>Recruitment workspace</span><div className="avatar">AQ</div></div></header>
   <section className="content"><div className="header-row"><div><div className="eyebrow">Recruitment operations</div><h1>Jobs &amp; Requisitions</h1><p className="subtitle">Move hiring demand through approval and into an operational vacancy.</p></div><button className="btn primary" onClick={()=>{setShowForm(v=>!v);setEditingId(null);setForm(initial);setMessage("");}}>{showForm?"Close form":"+ New requisition"}</button></div>
    <div className="stats-grid"><div className="stat-card"><div className="stat-label">Total in view</div><div className="stat-value">{loading?"—":count}</div></div><div className="stat-card"><div className="stat-label">Awaiting approval</div><div className="stat-value">{loading?"—":pending}</div></div><div className="stat-card"><div className="stat-label">Drafts / revisions</div><div className="stat-value">{loading?"—":drafts}</div></div><div className="stat-card"><div className="stat-label">Approved to convert</div><div className="stat-value">{loading?"—":approved}</div></div></div>
    {showForm&&<form className="card" onSubmit={create} style={{marginBottom:18}}><div className="card-head"><span className="card-title">{editingId?"Edit requisition draft":"New requisition draft"}</span><span className="muted-small">Approval is a separate action</span></div><div className="form-grid">
     <label>Job title<input required maxLength={200} value={form.title} onChange={e=>change("title",e.target.value)}/></label>
     <label>Department / team<input maxLength={160} value={form.department} onChange={e=>change("department",e.target.value)}/></label>
     <label>Headcount<input required type="number" min="1" max="10000" value={form.headcount} onChange={e=>change("headcount",e.target.value)}/></label>
     <label>Location<input value={form.location} onChange={e=>change("location",e.target.value)}/></label>
     <label>Country<select value={form.country_code} onChange={e=>change("country_code",e.target.value)}><option value="GB">United Kingdom</option><option value="US">United States</option><option value="IN">India</option><option value="AU">Australia</option></select></label>
     <label>Employment type<select value={form.employment_type} onChange={e=>change("employment_type",e.target.value)}><option>Permanent</option><option>Contract</option><option>Temporary</option><option>Internship</option><option>Part-time</option></select></label>
     <label>Work mode<select value={form.work_mode} onChange={e=>change("work_mode",e.target.value)}><option>Hybrid</option><option>On-site</option><option>Remote</option></select></label>
     <label>Assigned recruiter<select value={form.recruiter_id} onChange={e=>change("recruiter_id",e.target.value)}><option value="">Unassigned</option>{assignees.filter(a=>["owner","admin","recruiter"].includes(a.role)).map(a=><option key={a.user_id} value={a.user_id}>{a.full_name||a.email||a.user_id} · {a.role}</option>)}</select></label>
     <label>Hiring manager<select value={form.hiring_manager_id} onChange={e=>change("hiring_manager_id",e.target.value)}><option value="">Unassigned</option>{assignees.filter(a=>["owner","admin","hiring_manager"].includes(a.role)).map(a=><option key={a.user_id} value={a.user_id}>{a.full_name||a.email||a.user_id} · {a.role}</option>)}</select></label>
     <label>Salary currency<select value={form.salary_currency} onChange={e=>change("salary_currency",e.target.value)}><option>GBP</option><option>USD</option><option>INR</option><option>AUD</option></select></label>
     <label>Salary minimum<input type="number" min="0" value={form.salary_min} onChange={e=>change("salary_min",e.target.value)}/></label><label>Salary maximum<input type="number" min="0" value={form.salary_max} onChange={e=>change("salary_max",e.target.value)}/></label>
     <label className="span-2">Required skills, comma-separated<input value={form.required_skills} onChange={e=>change("required_skills",e.target.value)} placeholder="Python, SQL, stakeholder management"/></label>
     <label className="span-2">Business justification<textarea required minLength={1} maxLength={10000} value={form.justification} onChange={e=>change("justification",e.target.value)} rows={3} placeholder="Explain the business need, backfill or growth rationale."/></label>
    </div><div style={{display:"flex",gap:8,marginTop:16}}><button className="btn primary" disabled={saving}>{saving?(editingId?"Updating...":"Saving..."):(editingId?"Update draft":"Save draft")}</button><button type="button" className="btn" onClick={()=>setShowForm(false)}>Cancel</button></div></form>}
    {message&&<div className="notice" role="status">{message}</div>}
    <div className="card" style={{marginBottom:18}}><div style={{display:"flex",gap:10,alignItems:"center",flexWrap:"wrap"}}><select className="filter" value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">All statuses</option><option value="draft">Draft</option><option value="pending_approval">Awaiting approval</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="converted">Converted</option><option value="cancelled">Cancelled</option></select><span className="muted-small">{loading?"Loading…":count+" requisition"+(count===1?"":"s")+" in this view"}</span><button className="btn" onClick={()=>void load()} disabled={loading}>Refresh</button></div></div>
    <div className="card"><div className="card-head"><span className="card-title">Requisition register</span><span className="muted-small">{API_BASE?(loading?"Loading...":"Connected to API"):"API not configured"}</span></div><div style={{overflowX:"auto"}}><table className="table"><thead><tr><th><button className="btn" onClick={()=>sort("title")}>Requisition {sortBy==="title"?(sortDirection==="asc"?"↑":"↓"):"↕"}</button></th><th><button className="btn" onClick={()=>sort("department")}>Department {sortBy==="department"?(sortDirection==="asc"?"↑":"↓"):"↕"}</button></th><th><button className="btn" onClick={()=>sort("location")}>Location {sortBy==="location"?(sortDirection==="asc"?"↑":"↓"):"↕"}</button></th><th><button className="btn" onClick={()=>sort("headcount")}>Headcount {sortBy==="headcount"?(sortDirection==="asc"?"↑":"↓"):"↕"}</button></th><th><button className="btn" onClick={()=>sort("status")}>Status {sortBy==="status"?(sortDirection==="asc"?"↑":"↓"):"↕"}</button></th><th><button className="btn" onClick={()=>sort("updated_at")}>Updated {sortBy==="updated_at"?(sortDirection==="asc"?"↑":"↓"):"↕"}</button></th><th>Actions</th></tr></thead><tbody>
     {loading?<tr><td colSpan={7}>Loading requisitions…</td></tr>:rows.length===0?<tr><td colSpan={7}>No requisitions match this view.</td></tr>:visibleRows.map(row=><tr key={row.id}><td><strong>{row.title}</strong><div className="muted-small">{row.requisition_code}</div>{row.rejection_reason&&<div className="muted-small">Reason: {row.rejection_reason}</div>}</td><td>{row.department||"—"}</td><td>{row.location||"Not specified"}</td><td>{row.headcount}</td><td><span className={"badge "+(row.status==="approved"||row.status==="converted"?"green":row.status==="pending_approval"?"amber":row.status==="rejected"?"red":"blue")}>{labels[row.status]||row.status}</span></td><td>{new Date(row.updated_at).toLocaleDateString()}</td><td><div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
      {(row.status==="draft"||row.status==="rejected")&&<><button className="btn" disabled={busyId===row.id} onClick={()=>startEdit(row)}>Edit draft</button><button className="btn" disabled={busyId===row.id} onClick={()=>void act(row,"submit")}>Submit</button></>}
      {row.status==="pending_approval"&&<><button className="btn" disabled={busyId===row.id} onClick={()=>void act(row,"approve")}>Approve</button><button className="btn" disabled={busyId===row.id} onClick={()=>void act(row,"reject")}>Reject</button></>}
      {row.status==="approved"&&<button className="btn primary" disabled={busyId===row.id} onClick={()=>void act(row,"convert-to-job")}>Create job</button>}
      {row.job_id&&<Link className="btn" href={"/jobs?job_id="+row.job_id}>Open job</Link>}
     </div></td></tr>)}
    </tbody></table></div><div style={{display:"flex",gap:10,alignItems:"center",justifyContent:"space-between",flexWrap:"wrap",paddingTop:14}}><span className="muted-small">Showing {count===0?0:(page-1)*pageSize+1}–{Math.min(page*pageSize,count)} of {count} requisitions · Sorted by {sortBy.replace("_"," ")} ({sortDirection})</span><div style={{display:"flex",gap:8,alignItems:"center"}}><button className="btn" disabled={page<=1} onClick={()=>setPage(p=>Math.max(1,p-1))}>Previous</button><span className="muted-small">Page {page} of {totalPages}</span><button className="btn" disabled={page>=totalPages} onClick={()=>setPage(p=>Math.min(totalPages,p+1))}>Next</button></div></div></div><p className="muted-small" style={{marginTop:12}}>Approvals are enforced by the API. This first release uses organisation owners/admins as approvers; configurable multi-step approval chains are a later phase.</p>
   </section>
  </main>
 </div>;
}
