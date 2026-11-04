"""Chat event producer for the session-level SSE event bus."""

from __future__ import annotations

from uuid import UUID

import logfire

from api.agent.tools.data_model import ToolTaskResult

from .base_processor import BaseProcessor
from .session_streaming.events import (
    ChatReasoningDeltaEvent,
    ChatReasoningDeltaEventPayload,
    ChatStreamEndEvent,
    ChatStreamEndEventPayload,
    ChatTextMsgBeginEvent,
    ChatTextMsgBeginEventPayload,
    ChatTextMsgDeltaEvent,
    ChatTextMsgDeltaEventPayload,
    ChatTextMsgEndEvent,
    ChatTextMsgEndEventPayload,
    ChatToolCallEvent,
    ChatToolCallEventPayload,
    ChatToolResponseEvent,
    ChatToolResponseEventPayload,
    Outcome,
    SessionStreamEvent,
)
from .session_streaming.writer import publish_session_stream_event


class StreamingProcessor(BaseProcessor[SessionStreamEvent]):
    """Serialize chat channel events onto the session-level event stream."""

    def __init__(
        self,
        session_id: UUID,
        session_task_id: UUID,
        branch_name: str | None = None,
    ):
        super().__init__()
        self.session_id = session_id
        self.session_task_id = session_task_id
        self.branch_name = branch_name

    def _event_context(self) -> dict:
        return {
            "session_id": self.session_id,
            "session_task_id": self.session_task_id,
            "branch_name": self.branch_name,
        }

    async def _push(self, event: SessionStreamEvent) -> None:
        await self.push_message(event)

    async def push_text_start_msg(self) -> None:
        await self._push(
            ChatTextMsgBeginEvent(
                **self._event_context(),
                payload=ChatTextMsgBeginEventPayload(),
            ),
        )

    async def push_text_end_msg(self) -> None:
        await self._push(
            ChatTextMsgEndEvent(
                **self._event_context(),
                payload=ChatTextMsgEndEventPayload(),
            ),
        )

    async def push_text_delta_msg(self, delta: str) -> None:
        await self._push(
            ChatTextMsgDeltaEvent(
                **self._event_context(),
                payload=ChatTextMsgDeltaEventPayload(content=delta),
            ),
        )

    async def push_reasoning_delta_msg(self, delta: str) -> None:
        await self._push(
            ChatReasoningDeltaEvent(
                **self._event_context(),
                payload=ChatReasoningDeltaEventPayload(content=delta),
            ),
        )

    async def push_tool_call_msg(self, tool_exec_uuid: UUID, tool_name: str) -> None:
        await self._push(
            ChatToolCallEvent(
                **self._event_context(),
                payload=ChatToolCallEventPayload(
                    tool_exec_uuid=tool_exec_uuid,
                    tool_name=tool_name,
                ),
            ),
        )

    async def push_tool_response_msg(
        self,
        tool_exec_uuid: UUID,
        tool_result: ToolTaskResult | None,
    ) -> None:
        await self._push(
            ChatToolResponseEvent(
                **self._event_context(),
                payload=ChatToolResponseEventPayload(
                    tool_exec_uuid=tool_exec_uuid,
                    tool_result=(
                        tool_result.model_dump(mode="json")
                        if tool_result
                        else None
                    ),
                ),
            ),
        )

    async def push_stream_end(
        self,
        outcome: Outcome,
        error: str | None = None,
    ) -> None:
        """Queue the single task-level chat stream-end event."""
        await self._push(
            ChatStreamEndEvent(
                **self._event_context(),
                payload=ChatStreamEndEventPayload(
                    outcome=outcome,
                    error=error,
                ),
            ),
        )

    async def _process_message(self, event: SessionStreamEvent) -> None:
        """Write one queued event; UI push failures must not fail the agent task."""
        try:
            await publish_session_stream_event(event)
        except Exception:
            logfire.error(
                "streaming_processor: 会话事件写入失败",
                session_id=str(self.session_id),
                session_task_id=str(self.session_task_id),
                channel=event.channel,
                event_type=event.type,
            )
