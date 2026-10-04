"use client";
import { useEffect,useState } from "react";
const API_BASE=process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/,"")??"";
const ORG=process.env.NEXT_PUBLIC_ORGANIZATION_ID??"";
type Interview={id:string;application_id:string;scheduled_at:string;duration_minutes:number;interview_type:string;location?:string|null;status:string;notes?:string|null};
export default function InterviewsPage(){
 const [items,setItems]=useState<Interview[]>([]); const [loading,setLoading]=useState(true);
 useEffect(()=>{const org=localStorage.getItem("activeOrganizationId")||ORG; fetch(`${API_BASE}/api/interviews?organization_id=${org}`).then(r=>r.ok?r.json():[]).then(setItems).finally(()=>setLoading(false));},[]);
 return <main className="p-8"><h1 className="text-3xl font-semibold">Interviews</h1><p className="mt-2 text-sm text-gray-500">Manage candidate interviews and outcomes.</p><div className="mt-8 overflow-x-auto rounded-xl border"><table className="w-full text-left text-sm"><thead><tr className="border-b bg-gray-50"><th className="p-4">Scheduled</th><th className="p-4">Application</th><th className="p-4">Type</th><th className="p-4">Duration</th><th className="p-4">Status</th></tr></thead><tbody>{loading?<tr><td className="p-4" colSpan={5}>Loading…</td></tr>:items.map(i=><tr key={i.id} className="border-b"><td className="p-4">{new Date(i.scheduled_at).toLocaleString()}</td><td className="p-4 font-mono text-xs">{i.application_id}</td><td className="p-4">{i.interview_type}</td><td className="p-4">{i.duration_minutes} min</td><td className="p-4">{i.status}</td></tr>)}{!loading&&!items.length&&<tr><td className="p-4 text-gray-500" colSpan={5}>No interviews yet.</td></tr>}</tbody></table></div></main>;
}