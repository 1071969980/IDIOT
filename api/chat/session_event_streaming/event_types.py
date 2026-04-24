from __future__ import annotations

from typing import Literal, Union
from uuid import UUID

from pydantic import BaseModel


SessionEventType = Literal[
    "heartbeat",
    "branch_task_started",
    "branch_task_completed",
]

class SessionBranchTaskStartedEventPayload(BaseModel):
    """会话级 SSE 事件：会话任务开始。"""
    branch_name: str
    session_task_id: UUID

class SessionBranchTaskCompletedEventPayload(BaseModel):
    """会话级 SSE 事件：会话任务完成。"""
    branch_name: str
    session_task_id: UUID
    has_exception: bool

SessionEventPayloadType = Union[
    SessionBranchTaskStartedEventPayload,
    SessionBranchTaskCompletedEventPayload,
]

class SessionEventBase(BaseModel):
    """通用会话事件信封，所有会话级 SSE 事件继承此类。"""

    event_type: SessionEventType
    session_id: UUID
    payload: SessionEventPayloadType

class SessionBranchTaskStartedEvent(SessionEventBase):
    """会话级 SSE 事件：会话任务开始。"""
    event_type: SessionEventType = "branch_task_started"

class SessionBranchTaskCompletedEvent(SessionEventBase):
    """会话级 SSE 事件：会话任务完成。"""
    event_type: SessionEventType = "branch_task_completed"

