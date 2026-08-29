from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.jobs import router as jobs_router

app = FastAPI(
    title="ATS API",
    version="0.2.0",
    description="AI-powered Applicant Tracking System API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "ats-api"}
