import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.jobs import router as jobs_router
from app.routers.candidates import router as candidates_router
from app.routers.applications import router as applications_router
from app.routers.me import router as me_router
from app.routers.clients import router as clients_router


app = FastAPI(
    title="ATS API",
    version="0.7.0",
    description="AI-powered Applicant Tracking System API",
)

frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs_router)
app.include_router(candidates_router)
app.include_router(applications_router)
app.include_router(me_router)
app.include_router(clients_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok", "service": "ats-api", "docs": "/docs"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "ats-api"}
