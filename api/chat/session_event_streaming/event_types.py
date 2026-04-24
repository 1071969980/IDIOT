from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

SessionEventType = Literal[
    "heartbeat"
]

class SessionEventBase(BaseModel):
    """通用会话事件信封，所有会话级 SSE 事件继承此类。"""

    event_type: SessionEventType
    session_id: UUID
    payload: dict

