from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ChannelId = Literal["careers", "google", "linkedin", "indeed", "monster", "other"]
ChannelStatus = Literal["not_selected", "ready", "needs_public_page", "integration_required"]


class DistributionChannelIn(BaseModel):
    channel_id: ChannelId
    selected: bool
    status: ChannelStatus


class DistributionChannelOut(DistributionChannelIn):
    organization_id: UUID
    job_id: UUID
    updated_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class DistributionSave(BaseModel):
    channels: list[DistributionChannelIn] = Field(min_length=1, max_length=6)
