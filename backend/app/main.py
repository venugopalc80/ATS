import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers.jobs import router as jobs_router
from app.routers.candidates import router as candidates_router
from app.routers.applications import router as applications_router
from app.routers.me import router as me_router
from app.routers.clients import router as clients_router
from app.routers.dashboard import router as dashboard_router
from app.routers.interviews import router as interviews_router
from app.routers.interview_scorecards import router as interview_scorecards_router
from app.routers.offers import router as offers_router
from app.routers.placements import router as placements_router
from app.routers.audit import router as audit_router
from app.routers.notes import router as notes_router
from app.routers.job_distribution import router as job_distribution_router
from app.routers.public_jobs import router as public_jobs_router
from app.routers.documents import router as documents_router
from app.routers.assessments import router as assessments_router
from app.routers.recruitment_documents import router as recruitment_documents_router

app=FastAPI(title="AQERITH API",version="0.10.0",description="AQERITH recruitment operations API")
frontend_url=os.getenv("FRONTEND_URL","http://localhost:3000").rstrip("/")
frontend_origins = {
    origin.strip().rstrip("/")
    for origin in (
        frontend_url + ",https://aqerith.com,https://www.aqerith.com,https://aqerith-git-feat-inline-cv-preview-the-pixel-muses.vercel.app,https://aqerith-git-fix-dashboard-update-1-acceptance-the-pixel-muses.vercel.app,https://aqerith-r5t7uzo35-the-pixel-muses.vercel.app"
    ).split(",")
    if origin.strip()
}
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(frontend_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
for router in (
    jobs_router, candidates_router, applications_router, me_router, clients_router,
    dashboard_router, interviews_router, interview_scorecards_router, offers_router,
    placements_router, audit_router, notes_router, job_distribution_router,
    public_jobs_router, documents_router, assessments_router, recruitment_documents_router,
):
    app.include_router(router)

@app.get("/")
async def root()->dict[str,str]: return {"status":"ok","service":"aqerith-api","docs":"/docs"}

@app.get("/health")
async def health()->dict[str,str]: return {"status":"ok","service":"aqerith-api"}
