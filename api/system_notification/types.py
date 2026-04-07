from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class InternalNotification:
    """跨层统一通知数据类型。

    类型流转链路：SQL dataclass → InternalNotification → Pydantic NotificationItem
    """

    id: UUID
    level: str
    content: str
    created_at: datetime
    user_id: UUID | None = None
    session_id: UUID | None = None
