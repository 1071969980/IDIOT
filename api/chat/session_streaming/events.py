"""Typed events exchanged over the session-level SSE event bus.

The wire format is a nested discriminated union:

* the outer discriminator is ``channel``;
* the inner discriminator is ``type``;
* ``payload`` is always a JSON object with an event-specific model.

Only the event models are defined here. Redis I/O belongs to the writer layer.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from api.human_in_loop.data_model import (
    HILInterruptContent,
    HILNotificationContent,
)


Outcome = Literal["completed", "cancelled", "failed"]


class _EventModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _EventPayload(_EventModel):
    """Base class for all event payloads."""


# ---------------------------------------------------------------------------
# Session channel
# ---------------------------------------------------------------------------


class SessionBranchTaskStartedEventPayload(_EventPayload):
    """Payload for ``session.branch_task_started``; intentionally empty."""


class SessionBranchTaskCompletedEventPayload(_EventPayload):
    outcome: Outcome
    has_exception: bool


class SessionChannelEventBase(_EventModel):
    v: Literal[1] = 1
    channel: Literal["session"] = "session"
    session_id: UUID
    session_task_id: UUID
    branch_name: str | None = None


class SessionBranchTaskStartedEvent(SessionChannelEventBase):
    type: Literal["branch_task_started"] = "branch_task_started"
    payload: SessionBranchTaskStartedEventPayload


class SessionBranchTaskCompletedEvent(SessionChannelEventBase):
    type: Literal["branch_task_completed"] = "branch_task_completed"
    payload: SessionBranchTaskCompletedEventPayload


# ---------------------------------------------------------------------------
# Chat channel
# ---------------------------------------------------------------------------


class ChatTextMsgBeginEventPayload(_EventPayload):
    """Payload for ``chat.text_msg_begin``; intentionally empty."""


class ChatTextMsgDeltaEventPayload(_EventPayload):
    content: str


class ChatTextMsgEndEventPayload(_EventPayload):
    """Payload for ``chat.text_msg_end``; intentionally empty."""


class ChatReasoningDeltaEventPayload(_EventPayload):
    content: str


class ChatToolCallEventPayload(_EventPayload):
    tool_exec_uuid: UUID
    tool_name: str


class ChatToolResponseEventPayload(_EventPayload):
    tool_exec_uuid: UUID
    tool_result: dict[str, Any] | None


class ChatStreamEndEventPayload(_EventPayload):
    outcome: Outcome
    error: str | None


class ChatChannelEventBase(_EventModel):
    v: Literal[1] = 1
    channel: Literal["chat"] = "chat"
    session_id: UUID
    session_task_id: UUID
    branch_name: str | None = None


class ChatTextMsgBeginEvent(ChatChannelEventBase):
    type: Literal["text_msg_begin"] = "text_msg_begin"
    payload: ChatTextMsgBeginEventPayload


class ChatTextMsgDeltaEvent(ChatChannelEventBase):
    type: Literal["text_msg_delta"] = "text_msg_delta"
    payload: ChatTextMsgDeltaEventPayload


class ChatTextMsgEndEvent(ChatChannelEventBase):
    type: Literal["text_msg_end"] = "text_msg_end"
    payload: ChatTextMsgEndEventPayload


class ChatReasoningDeltaEvent(ChatChannelEventBase):
    type: Literal["reasoning_delta"] = "reasoning_delta"
    payload: ChatReasoningDeltaEventPayload


class ChatToolCallEvent(ChatChannelEventBase):
    type: Literal["tool_call"] = "tool_call"
    payload: ChatToolCallEventPayload


class ChatToolResponseEvent(ChatChannelEventBase):
    type: Literal["tool_response"] = "tool_response"
    payload: ChatToolResponseEventPayload


class ChatStreamEndEvent(ChatChannelEventBase):
    type: Literal["stream_end"] = "stream_end"
    payload: ChatStreamEndEventPayload


# ---------------------------------------------------------------------------
# HIL channel
# ---------------------------------------------------------------------------


class HilInterruptRequestEventPayload(_EventPayload):
    msg_id: str
    content: HILInterruptContent


class HilNotificationEventPayload(_EventPayload):
    msg_id: str
    content: HILNotificationContent


class HilStreamEndEventPayload(_EventPayload):
    """Payload for ``hil.stream_end``; intentionally empty."""


class HilChannelEventBase(_EventModel):
    v: Literal[1] = 1
    channel: Literal["hil"] = "hil"
    session_id: UUID
    session_task_id: UUID
    branch_name: str | None = None


class HilInterruptRequestEvent(HilChannelEventBase):
    type: Literal["HIL_interrupt_request"] = "HIL_interrupt_request"
    payload: HilInterruptRequestEventPayload


class HilNotificationEvent(HilChannelEventBase):
    type: Literal["Notification"] = "Notification"
    payload: HilNotificationEventPayload


class HilStreamEndEvent(HilChannelEventBase):
    type: Literal["stream_end"] = "stream_end"
    payload: HilStreamEndEventPayload


# ---------------------------------------------------------------------------
# Discriminated unions
# ---------------------------------------------------------------------------


SessionChannelEvent = Annotated[
    Union[
        SessionBranchTaskStartedEvent,
        SessionBranchTaskCompletedEvent,
    ],
    Field(discriminator="type"),
]

ChatChannelEvent = Annotated[
    Union[
        ChatTextMsgBeginEvent,
        ChatTextMsgDeltaEvent,
        ChatTextMsgEndEvent,
        ChatReasoningDeltaEvent,
        ChatToolCallEvent,
        ChatToolResponseEvent,
        ChatStreamEndEvent,
    ],
    Field(discriminator="type"),
]

HilChannelEvent = Annotated[
    Union[
        HilInterruptRequestEvent,
        HilNotificationEvent,
        HilStreamEndEvent,
    ],
    Field(discriminator="type"),
]

SessionStreamEvent = Annotated[
    Union[
        SessionChannelEvent,
        ChatChannelEvent,
        HilChannelEvent,
    ],
    Field(discriminator="channel"),
]

SessionStreamEventAdapter = TypeAdapter(SessionStreamEvent)

# Every v1 business event type, exported for event-catalog and test helpers.
SESSION_STREAM_EVENT_TYPES: tuple[str, ...] = (
    "session.branch_task_started",
    "session.branch_task_completed",
    "chat.text_msg_begin",
    "chat.text_msg_delta",
    "chat.text_msg_end",
    "chat.reasoning_delta",
    "chat.tool_call",
    "chat.tool_response",
    "chat.stream_end",
    "hil.HIL_interrupt_request",
    "hil.Notification",
    "hil.stream_end",
)
