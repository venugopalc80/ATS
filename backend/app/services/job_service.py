from typing import Any


class JobService:
    """Application service boundary for job requisitions.

    Persistence is intentionally injected later so API handlers do not become
    coupled to a specific database client.
    """

    async def list_jobs(self, organization_id: str) -> list[dict[str, Any]]:
        return []

    async def create_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        return payload
