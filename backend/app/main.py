import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.jobs import router as jobs_router


app = FastAPI(
    title="ATS API",
    version="0.2.1",
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


@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok", "service": "ats-api", "docs": "/docs"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "ats-api"}
