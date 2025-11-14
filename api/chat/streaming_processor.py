from typing import Literal, TypedDict
from uuid import UUID

import ujson
from openai.types.chat import ChatCompletionMessageToolCall
from openai.types.chat.chat_completion_chunk import ChoiceDeltaToolCall
from openai.types.chat.chat_completion_tool_message_param import (
    ChatCompletionToolMessageParam,
)
from pydantic import BaseModel

from api.redis.constants import CLIENT as redis_client

from .base_processor import BaseProcessor

StreamingMessageType = Literal[
    "status_begin",
    "status_update",
    "status_end",
    "text_msg_begin",
    "text_msg_end",
    "text_msg_delta",
    "tool_call",
    "tool_response",
    "stream_end",
]

class StreamingMessage(BaseModel):
    ss_task_uuid: UUID
    type: StreamingMessageType
    content: str | None = None

class StreamingMessageDict(TypedDict):
    ss_task_uuid: str
    type: str
    content: str | None
    


class StreamingProcessor(BaseProcessor[StreamingMessage]):
    """Processor for streaming messages to Redis with OpenAI API compatibility."""

    def __init__(
        self,
        task_uuid: UUID,
        expiration_seconds: int = 3600,
    ):
        """Initialize the StreamingProcessor.

        Args:
            session_uuid: Session UUID for stream key generation
            expiration_seconds: Expiration time for stream entries in seconds
        """
        super().__init__()
        self.task_uuid = task_uuid
        self.expiration_seconds = expiration_seconds
        self._stream_key = f"u2a_msg_stream:{self.task_uuid}"


    async def push_status_begin_msg(self, data: dict) -> None:
        """Send a status begin message to Redis stream."""
        await self.push_message(
            StreamingMessage(
                ss_task_uuid=self.task_uuid,
                type="status_begin",
                content=ujson.dumps(data, ensure_ascii=False),
            ),
        )

    async def push_status_update_msg(self, data: dict) -> None:
        """Send a status update message to Redis stream."""
        await self.push_message(
            StreamingMessage(
                ss_task_uuid=self.task_uuid,
                type="status_update",
                content=ujson.dumps(data, ensure_ascii=False),
            ),
        )
    
    async def push_status_end_msg(self, data: dict) -> None:
        """Send a status end message to Redis stream."""
        await self.push_message(
            StreamingMessage(
                ss_task_uuid=self.task_uuid,
                type="status_end",
                content=ujson.dumps(data, ensure_ascii=False),
            ),
        )


    async def push_text_start_msg(self) -> None:
        """Send a starting message to Redis stream."""
        await self.push_message(
            StreamingMessage(
                ss_task_uuid=self.task_uuid,
                type="text_msg_begin",
            ),
        )

    async def push_text_end_msg(self) -> None:
        """Send an ending message to Redis stream."""
        await self.push_message(
            StreamingMessage(
                ss_task_uuid=self.task_uuid,
                type="text_msg_end",
            ),
        )
    
    async def push_text_delta_msg(self, delta: str) -> None:
        """Send a delta message to Redis stream."""
        await self.push_message(
            StreamingMessage(
                ss_task_uuid=self.task_uuid,
                type="text_msg_delta",
                content=delta,
            ),
        )
    
    async def push_tool_call_msg(self,
                           tool_call: ChatCompletionMessageToolCall | ChoiceDeltaToolCall) -> None:
        """Send a tool call message to Redis stream."""
        await self.push_message(
            StreamingMessage(
                ss_task_uuid=self.task_uuid,
                type="tool_call",
                content=tool_call.model_dump_json(),
            ),
        )
    
    async def push_tool_response_msg(self, tool_response: ChatCompletionToolMessageParam) -> None:
        """Send a tool response message to Redis stream."""
        await self.push_message(
            StreamingMessage(
                ss_task_uuid=self.task_uuid,
                type="tool_response",
                content=ujson.dumps(tool_response, ensure_ascii=False),
            ),
        )


    async def push_exception_ending_message(self, e: Exception) -> None:
        """Send an ending message to Redis stream."""
        await self.push_message(
            StreamingMessage(
                ss_task_uuid=self.task_uuid,
                type="stream_end",
                content=str(e),
            ),
        )

    async def push_ending_message(self) -> None:
        """Send an ending message to Redis stream."""
        await self.push_message(
            StreamingMessage(
                ss_task_uuid=self.task_uuid,
                type="stream_end",
            ),
        )
    
    async def _process_message(self, chunk: StreamingMessage) -> None:
        """Process a single ChatCompletionChunk by sending it to Redis stream.

        Args:
            chunk: The ChatCompletionChunk to process
        """
        # Use pydantic BaseModel's dict() method for serialization
        message_dict = chunk.model_dump(mode="json")

        try:
            # Add to Redis stream using existing redis client
            await redis_client.xadd(
                self._stream_key,
                message_dict, # type: ignore
            )

            # Set expiration for the entire stream
            await redis_client.expire(
                self._stream_key,
                self.expiration_seconds,
            )

        except Exception as e:
            print(f"Error sending message to Redis stream: {e}")

