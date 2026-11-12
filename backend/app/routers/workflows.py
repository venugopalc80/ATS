from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import assert_org_admin, assert_org_member, get_current_user_id
from app.db import DatabaseConfigurationError, DatabaseConnectionError
from app.schemas.workflows import WorkflowDefinitionPayload, preview_workflow
from app.services.workflow_service import (
    create_workflow, disable_workflow, get_workflow, list_workflow_runs,
    list_workflows, publish_workflow, update_workflow,
)

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


class WorkflowPreviewRequest(BaseModel):
    event_name: str
    event_payload: dict = Field(default_factory=dict)


def _database_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="Database operation failed")


@router.get("")
def get_workflows(organization_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, organization_id)
    try:
        return list_workflows(organization_id)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc


@router.post("", status_code=201)
def post_workflow(
    organization_id: UUID,
    payload: WorkflowDefinitionPayload,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    try:
        return create_workflow(organization_id, user_id, payload)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc


@router.get("/runs")
def get_workflow_runs(
    organization_id: UUID,
    workflow_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    try:
        return list_workflow_runs(organization_id, workflow_id, limit)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc


@router.get("/{workflow_id}")
def get_one_workflow(workflow_id: UUID, organization_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    assert_org_member(user_id, organization_id)
    try:
        workflow = get_workflow(organization_id, workflow_id)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@router.put("/{workflow_id}")
def put_workflow(
    workflow_id: UUID,
    organization_id: UUID,
    payload: WorkflowDefinitionPayload,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    try:
        workflow = update_workflow(organization_id, workflow_id, user_id, payload)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc
    if workflow is None:
        raise HTTPException(status_code=409, detail="Workflow not found or not editable in its current state")
    return workflow


@router.post("/{workflow_id}/preview")
def preview_one_workflow(
    workflow_id: UUID,
    organization_id: UUID,
    payload: WorkflowPreviewRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    assert_org_member(user_id, organization_id)
    try:
        workflow = get_workflow(organization_id, workflow_id)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    definition = WorkflowDefinitionPayload.model_validate(workflow["draft_definition"])
    return preview_workflow(definition, payload.event_name, payload.event_payload)


@router.post("/{workflow_id}/publish")
def publish_one_workflow(
    workflow_id: UUID, organization_id: UUID, user_id: UUID = Depends(get_current_user_id)
):
    assert_org_admin(user_id, organization_id)
    try:
        workflow = publish_workflow(organization_id, workflow_id, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@router.post("/{workflow_id}/disable")
def disable_one_workflow(
    workflow_id: UUID, organization_id: UUID, user_id: UUID = Depends(get_current_user_id)
):
    assert_org_admin(user_id, organization_id)
    try:
        workflow = disable_workflow(organization_id, workflow_id, user_id)
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise _database_error(exc) from exc
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow
