"""Persistence for workflow definitions and immutable published versions."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from app.db import get_connection
from app.schemas.workflows import WorkflowDefinitionPayload


def _definition_dict(definition: WorkflowDefinitionPayload) -> dict[str, Any]:
    return definition.model_dump(mode="json")


def list_workflows(organization_id: UUID) -> list[dict[str, Any]]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """select id, organization_id, name, description, status, active_version_id,
                          created_by, updated_by, created_at, updated_at
                   from public.workflow_definitions
                   where organization_id=%s
                   order by updated_at desc""",
                [organization_id],
            )
            return list(cursor.fetchall())


def get_workflow(organization_id: UUID, workflow_id: UUID) -> dict[str, Any] | None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """select id, organization_id, name, description, status, active_version_id,
                          draft_definition, created_by, updated_by, created_at, updated_at
                   from public.workflow_definitions
                   where organization_id=%s and id=%s""",
                [organization_id, workflow_id],
            )
            return cursor.fetchone()


def create_workflow(
    organization_id: UUID, user_id: UUID, definition: WorkflowDefinitionPayload
) -> dict[str, Any]:
    value = _definition_dict(definition)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """insert into public.workflow_definitions
                     (organization_id, name, description, draft_definition, created_by, updated_by)
                   values (%s,%s,%s,%s::jsonb,%s,%s)
                   returning id, organization_id, name, description, status, active_version_id,
                             draft_definition, created_by, updated_by, created_at, updated_at""",
                [organization_id, definition.name, definition.description,
                 json.dumps(value), user_id, user_id],
            )
            return cursor.fetchone()


def update_workflow(
    organization_id: UUID, workflow_id: UUID, user_id: UUID,
    definition: WorkflowDefinitionPayload
) -> dict[str, Any] | None:
    value = _definition_dict(definition)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """update public.workflow_definitions
                   set name=%s, description=%s, draft_definition=%s::jsonb,
                       updated_by=%s, updated_at=now()
                   where organization_id=%s and id=%s and status <> 'published'
                   returning id, organization_id, name, description, status, active_version_id,
                             draft_definition, created_by, updated_by, created_at, updated_at""",
                [definition.name, definition.description, json.dumps(value), user_id,
                 organization_id, workflow_id],
            )
            return cursor.fetchone()


def publish_workflow(organization_id: UUID, workflow_id: UUID, user_id: UUID) -> dict[str, Any] | None:
    """Publish a validated snapshot and pin it as the active version in one transaction."""
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """select id, name, description, draft_definition, status
                   from public.workflow_definitions
                   where organization_id=%s and id=%s
                   for update""",
                [organization_id, workflow_id],
            )
            workflow = cursor.fetchone()
            if workflow is None:
                return None
            if workflow["status"] == "disabled":
                raise ValueError("Disabled workflows must be re-enabled through an explicit review")
            definition = WorkflowDefinitionPayload.model_validate(workflow["draft_definition"])
            cursor.execute(
                "select coalesce(max(version_number), 0) + 1 as next_version from public.workflow_versions where workflow_id=%s",
                [workflow_id],
            )
            version_number = cursor.fetchone()["next_version"]
            cursor.execute(
                """insert into public.workflow_versions
                     (organization_id, workflow_id, version_number, trigger_event, definition, created_by, published_at)
                   values (%s,%s,%s,%s,%s::jsonb,%s,now())
                   returning id, version_number, published_at""",
                [organization_id, workflow_id, version_number, definition.trigger_event,
                 json.dumps(_definition_dict(definition)), user_id],
            )
            version = cursor.fetchone()
            cursor.execute(
                """update public.workflow_definitions
                   set status='published', active_version_id=%s, updated_by=%s, updated_at=now()
                   where organization_id=%s and id=%s
                   returning id, organization_id, name, description, status, active_version_id,
                             created_by, updated_by, created_at, updated_at""",
                [version["id"], user_id, organization_id, workflow_id],
            )
            result = cursor.fetchone()
            result["published_version"] = version
            return result


def disable_workflow(organization_id: UUID, workflow_id: UUID, user_id: UUID) -> dict[str, Any] | None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """update public.workflow_definitions
                   set status='disabled', updated_by=%s, updated_at=now()
                   where organization_id=%s and id=%s
                   returning id, organization_id, name, description, status, active_version_id,
                             created_by, updated_by, created_at, updated_at""",
                [user_id, organization_id, workflow_id],
            )
            return cursor.fetchone()


def list_workflow_runs(
    organization_id: UUID, workflow_id: UUID | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            if workflow_id:
                cursor.execute(
                    """select id, organization_id, workflow_id, workflow_version_id, event_name,
                              event_id, status, result_summary, error_code, error_message, attempts,
                              next_action_at, started_at, completed_at, created_at, updated_at
                       from public.workflow_runs
                       where organization_id=%s and workflow_id=%s
                       order by created_at desc limit %s""",
                    [organization_id, workflow_id, limit],
                )
            else:
                cursor.execute(
                    """select id, organization_id, workflow_id, workflow_version_id, event_name,
                              event_id, status, result_summary, error_code, error_message, attempts,
                              next_action_at, started_at, completed_at, created_at, updated_at
                       from public.workflow_runs where organization_id=%s
                       order by created_at desc limit %s""",
                    [organization_id, limit],
                )
            return list(cursor.fetchall())
