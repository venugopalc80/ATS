"use client";
import { useEffect,useState } from "react";
import { apiFetch } from "@/lib/api";
const API_BASE=process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/,"")??"";
const ORG=process.env.NEXT_PUBLIC_ORGANIZATION_ID??"";
type Offer={id:string;application_id:string;title:string;status:string;employment_type?:string|null;start_date?:string|null;salary_amount?:number|null;salary_currency?:string|null};
export default function OffersPage(){
 const [items,setItems]=useState<Offer[]>([]); const [loading,setLoading]=useState(true);
 useEffect(()=>{const org=localStorage.getItem("talentos_active_org")||ORG; apiFetch(`${API_BASE}/api/offers?organization_id=${org}`).then(r=>r.ok?r.json():[]).then(setItems).finally(()=>setLoading(false));},[]);
 return <main className="p-8"><h1 className="text-3xl font-semibold">Offers</h1><p className="mt-2 text-sm text-gray-500">Track offers from draft through acceptance.</p><div className="mt-8 overflow-x-auto rounded-xl border"><table className="w-full text-left text-sm"><thead><tr className="border-b bg-gray-50"><th className="p-4">Title</th><th className="p-4">Application</th><th className="p-4">Salary</th><th className="p-4">Start date</th><th className="p-4">Status</th></tr></thead><tbody>{loading?<tr><td className="p-4" colSpan={5}>Loading…</td></tr>:items.map(o=><tr key={o.id} className="border-b"><td className="p-4 font-medium">{o.title}</td><td className="p-4 font-mono text-xs">{o.application_id}</td><td className="p-4">{o.salary_amount!=null?`${o.salary_currency||""} ${o.salary_amount}`:"—"}</td><td className="p-4">{o.start_date||"—"}</td><td className="p-4">{o.status}</td></tr>)}{!loading&&!items.length&&<tr><td className="p-4 text-gray-500" colSpan={5}>No offers yet.</td></tr>}</tbody></table></div></main>;
}