from __future__ import annotations

from typing import Literal, Union
from uuid import UUID

from pydantic import BaseModel


SessionEventType = Literal[
    "heartbeat",
    "branch_task_started",
    "branch_task_completed",
    "mem_recall_started",
    "mem_recall_completed",
    "mem_write_started",
    "mem_write_completed",
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

class SessionMemRecallStartedEventPayload(BaseModel):
    """会话级 SSE 事件：记忆召回开始。"""
    session_task_id: UUID

class SessionMemRecallCompletedEventPayload(BaseModel):
    """会话级 SSE 事件：记忆召回完成。"""
    session_task_id: UUID
    has_exception: bool

class SessionMemWriteStartedEventPayload(BaseModel):
    """会话级 SSE 事件：记忆写入开始。"""
    session_task_id: UUID

class SessionMemWriteCompletedEventPayload(BaseModel):
    """会话级 SSE 事件：记忆写入完成。"""
    session_task_id: UUID
    has_exception: bool

SessionEventPayloadType = Union[
    SessionBranchTaskStartedEventPayload,
    SessionBranchTaskCompletedEventPayload,
    SessionMemRecallStartedEventPayload,
    SessionMemRecallCompletedEventPayload,
    SessionMemWriteStartedEventPayload,
    SessionMemWriteCompletedEventPayload,
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

class SessionMemRecallStartedEvent(SessionEventBase):
    """会话级 SSE 事件：记忆召回开始。"""
    event_type: SessionEventType = "mem_recall_started"

class SessionMemRecallCompletedEvent(SessionEventBase):
    """会话级 SSE 事件：记忆召回完成。"""
    event_type: SessionEventType = "mem_recall_completed"

class SessionMemWriteStartedEvent(SessionEventBase):
    """会话级 SSE 事件：记忆写入开始。"""
    event_type: SessionEventType = "mem_write_started"

class SessionMemWriteCompletedEvent(SessionEventBase):
    """会话级 SSE 事件：记忆写入完成。"""
    event_type: SessionEventType = "mem_write_completed"
