from uuid import UUID

from app.db import get_connection

ASSIGNMENT_COLUMNS = (
    "application_id, organization_id, recruiter_id, assigned_by, assigned_at, updated_at"
)
HISTORY_COLUMNS = (
    "id, organization_id, application_id, previous_recruiter_id, "
    "new_recruiter_id, actor_user_id, reason, created_at"
)


class ApplicationAssignmentService:
    async def assign(
        self,
        application_id: UUID,
        recruiter_id: UUID | None,
        actor_user_id: UUID,
        reason: str,
    ) -> dict | None:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select organization_id from public.applications where id=%s for update",
                    [application_id],
                )
                application = cursor.fetchone()
                if application is None:
                    return None
                organization_id = application["organization_id"]

                if recruiter_id is not None:
                    cursor.execute(
                        "select role from public.organization_members "
                        "where organization_id=%s and user_id=%s",
                        [organization_id, recruiter_id],
                    )
                    member = cursor.fetchone()
                    if member is None or member["role"] != "recruiter":
                        raise ValueError("Assignee must be a recruiter in this organisation")

                cursor.execute(
                    "select recruiter_id from public.application_assignments "
                    "where application_id=%s for update",
                    [application_id],
                )
                previous = cursor.fetchone()
                previous_recruiter_id = previous["recruiter_id"] if previous else None

                cursor.execute(
                    "insert into public.application_assignments "
                    "(application_id, organization_id, recruiter_id, assigned_by, assigned_at, updated_at) "
                    "values (%s, %s, %s, %s, case when %s is null then null else now() end, now()) "
                    "on conflict (application_id) do update set "
                    "recruiter_id=excluded.recruiter_id, assigned_by=excluded.assigned_by, "
                    "assigned_at=excluded.assigned_at, updated_at=now() "
                    "returning " + ASSIGNMENT_COLUMNS,
                    [application_id, organization_id, recruiter_id, actor_user_id, recruiter_id],
                )
                assignment = cursor.fetchone()
                if previous_recruiter_id != recruiter_id:
                    cursor.execute(
                        "insert into public.application_assignment_history "
                        "(organization_id, application_id, previous_recruiter_id, "
                        "new_recruiter_id, actor_user_id, reason) "
                        "values (%s, %s, %s, %s, %s, %s)",
                        [organization_id, application_id, previous_recruiter_id,
                         recruiter_id, actor_user_id, reason],
                    )
                return assignment

    async def get(self, application_id: UUID, organization_id: UUID) -> dict | None:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select " + ASSIGNMENT_COLUMNS + " from public.application_assignments "
                    "where application_id=%s and organization_id=%s",
                    [application_id, organization_id],
                )
                return cursor.fetchone()

    async def history(self, application_id: UUID, organization_id: UUID) -> list[dict]:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select " + HISTORY_COLUMNS + " from public.application_assignment_history "
                    "where application_id=%s and organization_id=%s "
                    "order by created_at desc, id desc",
                    [application_id, organization_id],
                )
                return list(cursor.fetchall())
