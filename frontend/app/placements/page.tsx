"use client";
import { useEffect,useState } from "react";
import { apiFetch } from "@/lib/api";
const API_BASE=process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/,"")??"";
const ORG=process.env.NEXT_PUBLIC_ORGANIZATION_ID??"";
type Placement={id:string;candidate_id:string;job_id:string;client_id?:string|null;status:string;start_date:string;end_date?:string|null;fee_amount?:number|null;fee_currency?:string|null;fee_type?:string|null};
export default function PlacementsPage(){
 const [items,setItems]=useState<Placement[]>([]); const [loading,setLoading]=useState(true);
 useEffect(()=>{const org=localStorage.getItem("talentos_active_org")||ORG; apiFetch(`${API_BASE}/api/placements?organization_id=${org}`).then(r=>r.ok?r.json():[]).then(setItems).finally(()=>setLoading(false));},[]);
 return <main className="p-8"><h1 className="text-3xl font-semibold">Placements</h1><p className="mt-2 text-sm text-gray-500">Track successful hires and recruitment fees.</p><div className="mt-8 overflow-x-auto rounded-xl border"><table className="w-full text-left text-sm"><thead><tr className="border-b bg-gray-50"><th className="p-4">Candidate</th><th className="p-4">Job</th><th className="p-4">Start</th><th className="p-4">Fee</th><th className="p-4">Status</th></tr></thead><tbody>{loading?<tr><td className="p-4" colSpan={5}>Loading…</td></tr>:items.map(p=><tr key={p.id} className="border-b"><td className="p-4 font-mono text-xs">{p.candidate_id}</td><td className="p-4 font-mono text-xs">{p.job_id}</td><td className="p-4">{p.start_date}</td><td className="p-4">{p.fee_amount!=null?`${p.fee_currency||""} ${p.fee_amount}${p.fee_type==="percentage"?"%":""}`:"—"}</td><td className="p-4">{p.status}</td></tr>)}{!loading&&!items.length&&<tr><td className="p-4 text-gray-500" colSpan={5}>No placements yet.</td></tr>}</tbody></table></div></main>;
}