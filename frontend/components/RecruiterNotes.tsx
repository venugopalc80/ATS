"use client";
import {useEffect,useState} from "react";
import {apiFetch} from "@/lib/api";
const A=process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/,"")??"";
const O=process.env.NEXT_PUBLIC_ORGANIZATION_ID??"";
export default function RecruiterNotes({candidateId}:{candidateId:string}){
 const [notes,setNotes]=useState<any[]>([]),[draft,setDraft]=useState(""),[busy,setBusy]=useState(false);
 const org=typeof window!=="undefined"?(localStorage.getItem("talentos_active_org")||O):O;
 useEffect(()=>{void(async()=>{const r=await apiFetch(A+"/api/notes/candidate/"+candidateId+"?organization_id="+encodeURIComponent(org));if(r.ok)setNotes(await r.json())})()},[candidateId,org]);
 async function add(){if(!draft.trim())return;setBusy(true);const r=await apiFetch(A+"/api/notes",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({organization_id:org,candidate_id:candidateId,note:draft})});if(r.ok){setNotes([await r.json(),...notes]);setDraft("")}setBusy(false)}
 return <section className="card mt-5"><div className="card-head"><span className="card-title">Recruiter notes</span><span className="muted-small">{notes.length}</span></div><textarea rows={4} value={draft} onChange={e=>setDraft(e.target.value)} placeholder="Add a private recruiter note..."/><button className="btn primary mt-3" disabled={busy||!draft.trim()} onClick={()=>void add()}>{busy?"Saving...":"Add note"}</button><div className="mt-5 space-y-4">{notes.map(n=><div key={n.id} className="border-b pb-4"><p className="whitespace-pre-wrap">{n.note}</p><div className="muted-small mt-1">{new Date(n.created_at).toLocaleString()}</div></div>)}</div></section>
}