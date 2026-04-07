from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

NotificationLevel = Literal["Low", "Normal", "High", "Urgent"]


class NotificationItem(BaseModel):
    id: UUID
    level: NotificationLevel
    content: str
    created_at: datetime


class NotificationListResponse(BaseModel):
    notifications: list[NotificationItem]


class PaginationParams(BaseModel):
    limit: int | None = None
    offset: int | None = None
