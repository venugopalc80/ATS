from uuid import UUID

from app.db import get_connection
from app.schemas.rate_cards import RateCardCreate, RateCardUpdate

COLUMNS = """id, organization_id, client_id, job_id, name, employment_type,
rate_basis, currency, rate_amount, fee_percentage, effective_from, effective_to,
status, version, notes, created_by, created_at, updated_at"""

COMMERCIAL_FIELDS = {
    "job_id", "name", "employment_type", "rate_basis", "currency", "rate_amount",
    "fee_percentage", "effective_from", "effective_to", "notes",
}
ALLOWED_STATUS_TRANSITIONS = {
    "draft": {"active", "archived"},
    "active": {"expired", "archived"},
    "expired": {"archived"},
    "archived": set(),
}


def _validate_terms(data: dict, existing: dict | None = None) -> None:
    merged = dict(existing or {})
    merged.update(data)
    if merged.get("effective_to") is not None and merged.get("effective_to") < merged.get("effective_from"):
        raise ValueError("Effective end date cannot be before the start date")
    basis = merged.get("rate_basis")
    amount = merged.get("rate_amount")
    percentage = merged.get("fee_percentage")
    if basis == "percentage_fee":
        if percentage is None or percentage <= 0 or percentage > 100 or amount is not None:
            raise ValueError("Percentage fee requires a fee percentage between 0 and 100 and no rate amount")
    elif amount is None or amount < 0 or percentage is not None:
        raise ValueError("This rate basis requires a non-negative rate amount and no fee percentage")


class RateCardService:
    async def list_rate_cards(
        self, organization_id: UUID, client_id: UUID | None = None,
        status: str | None = None, include_archived: bool = False,
    ):
        query = f"select {COLUMNS} from public.rate_cards where organization_id=%s"
        params = [organization_id]
        if client_id:
            query += " and client_id=%s"
            params.append(client_id)
        if status:
            query += " and status=%s"
            params.append(status)
        elif not include_archived:
            query += " and status <> 'archived'"
        query += " order by client_id, name, version desc, effective_from desc"
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                return list(cursor.fetchall())

    async def create_rate_card(self, payload: RateCardCreate, actor_user_id: UUID):
        data = payload.model_dump(mode="python")
        data["name"] = payload.name.strip()
        _validate_terms(data)
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select id from public.clients where id=%s and organization_id=%s",
                    [payload.client_id, payload.organization_id],
                )
                if cursor.fetchone() is None:
                    raise ValueError("Client must belong to the same organisation")
                if payload.job_id is not None:
                    cursor.execute(
                        "select client_id from public.jobs where id=%s and organization_id=%s",
                        [payload.job_id, payload.organization_id],
                    )
                    job = cursor.fetchone()
                    if job is None:
                        raise ValueError("Job must belong to the same organisation")
                    if job.get("client_id") is not None and job["client_id"] != payload.client_id:
                        raise ValueError("Rate card client must match the job's client")

                # Serialise version allocation for the same client/job/name.
                lock_key = f"{payload.organization_id}:{payload.client_id}:{payload.job_id or 'none'}:{data['name'].casefold()}"
                cursor.execute("select pg_advisory_xact_lock(hashtextextended(%s, 0))", [lock_key])
                cursor.execute(
                    """select coalesce(max(version), 0) as max_version
                       from public.rate_cards
                       where organization_id=%s and client_id=%s
                         and job_id is not distinct from %s and lower(name)=lower(%s)""",
                    [payload.organization_id, payload.client_id, payload.job_id, data["name"]],
                )
                data["version"] = cursor.fetchone()["max_version"] + 1
                data["created_by"] = actor_user_id
                cursor.execute("select set_config('app.actor_user_id', %s, true)", [str(actor_user_id)])
                columns = list(data)
                cursor.execute(
                    f"insert into public.rate_cards ({','.join(columns)}) "
                    f"values ({','.join(['%s'] * len(columns))}) returning {COLUMNS}",
                    [data[column] for column in columns],
                )
                return cursor.fetchone()

    async def get_rate_card(self, organization_id: UUID, rate_card_id: UUID):
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"select {COLUMNS} from public.rate_cards where id=%s and organization_id=%s",
                    [rate_card_id, organization_id],
                )
                return cursor.fetchone()

    async def update_rate_card(
        self, organization_id: UUID, rate_card_id: UUID,
        payload: RateCardUpdate, actor_user_id: UUID,
    ):
        data = payload.model_dump(mode="python", exclude_unset=True)
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"select {COLUMNS} from public.rate_cards where id=%s and organization_id=%s for update",
                    [rate_card_id, organization_id],
                )
                existing = cursor.fetchone()
                if existing is None:
                    return None
                if not data:
                    return existing

                current_status = existing["status"]
                next_status = data.get("status", current_status)
                if next_status != current_status and next_status not in ALLOWED_STATUS_TRANSITIONS[current_status]:
                    raise ValueError("Invalid rate-card status transition")

                changed_commercial_fields = COMMERCIAL_FIELDS.intersection(data)
                if current_status != "draft" and changed_commercial_fields:
                    raise ValueError("Commercial terms on a non-draft rate card are immutable; create a new version instead")

                merged = dict(existing)
                merged.update(data)
                _validate_terms(merged)
                if "name" in data and data["name"] is not None:
                    data["name"] = data["name"].strip()

                if "job_id" in data and data["job_id"] is not None:
                    cursor.execute(
                        "select client_id from public.jobs where id=%s and organization_id=%s",
                        [data["job_id"], organization_id],
                    )
                    job = cursor.fetchone()
                    if job is None:
                        raise ValueError("Job must belong to the same organisation")
                    if job.get("client_id") is not None and job["client_id"] != existing["client_id"]:
                        raise ValueError("Rate card client must match the job's client")

                if next_status == "active" and current_status != "active":
                    effective_from = merged["effective_from"]
                    effective_to = merged["effective_to"]
                    cursor.execute(
                        """select id from public.rate_cards
                           where organization_id=%s and client_id=%s
                             and job_id is not distinct from %s and lower(name)=lower(%s)
                             and status='active' and id<>%s
                             and (effective_to is null or effective_to >= %s)
                             and (%s is null or effective_from <= %s)
                           limit 1""",
                        [organization_id, existing["client_id"], merged["job_id"], merged["name"],
                         rate_card_id, effective_from, effective_to, effective_to],
                    )
                    if cursor.fetchone() is not None:
                        raise ValueError("An active rate-card version already overlaps this effective period")

                cursor.execute("select set_config('app.actor_user_id', %s, true)", [str(actor_user_id)])
                assignments = ",".join(f"{key}=%s" for key in data)
                cursor.execute(
                    f"update public.rate_cards set {assignments},updated_at=now() "
                    f"where id=%s and organization_id=%s returning {COLUMNS}",
                    list(data.values()) + [rate_card_id, organization_id],
                )
                return cursor.fetchone()
