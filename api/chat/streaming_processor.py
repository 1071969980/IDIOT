import json
import uuid
from datetime import datetime, UTC
from typing import Literal
from pydantic import BaseModel
from .base_processor import BaseProcessor
from api.redis.constants import CLIENT as redis_client

StreamingMessageType = Literal[
    "status_begin",
    "status_end",
    "text_msg_begin",
    "text_msg_end",
    "text_msg_delta",
    "tool_call",
    "tool_response",
    "stream_end"
]

class StreamingMessage(BaseModel):
    ss_uuid: str
    msg_uuid: str
    type: StreamingMessageType
    content: str | None = None
    


class StreamingProcessor(BaseProcessor[StreamingMessage]):
    """Processor for streaming messages to Redis with OpenAI API compatibility."""

    def __init__(
        self,
        task_uuid: str,
        expiration_seconds: int = 3600
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


    async def _process_message(self, chunk: StreamingMessage) -> None:
        """Process a single ChatCompletionChunk by sending it to Redis stream.

        Args:
            chunk: The ChatCompletionChunk to process
        """
        # Use pydantic BaseModel's dict() method for serialization
        message_dict = chunk.model_dump()

        try:
            # Add to Redis stream using existing redis client
            await redis_client.xadd(
                self._stream_key,
                message_dict
            )

            # Set expiration for the entire stream
            await redis_client.expire(
                self._stream_key,
                self.expiration_seconds
            )

        except Exception as e:
            print(f"Error sending message to Redis stream: {e}")

