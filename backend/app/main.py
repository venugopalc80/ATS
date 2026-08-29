from fastapi import FastAPI

app = FastAPI(
    title="ATS API",
    version="0.1.0",
    description="AI-powered Applicant Tracking System API",
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "ats-api"}
