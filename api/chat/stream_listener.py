import asyncio
from typing import AsyncGenerator, Optional
from uuid import UUID

from api.redis.constants import CLIENT

async def u2a_msg_stream_generator(
    task_uuid: UUID,
    start_id: str = "0",
    block_ms: int = 10000,
    count: Optional[int] = 1,
    check_stream_existence: bool = True,
    stream_existence_check_interval: int = 1,
    max_stream_existence_check_retries: int = 10,
    max_read_retries: int = 1000
) -> AsyncGenerator[tuple[str, dict[str, str]], None]:
    """
    Listen to and yield messages from a Redis stream with message ID and parsed data.
    Stops when receiving a message with type 'stream_end' or when retry limits are reached.

    Args:
        task_uuid: Session task UUID for stream key generation
        start_id: Starting message ID (default: "0" for beginning of stream)
        block_ms: Block time in milliseconds (default: 10 seconds)
        count: Number of messages to read per call (None for unlimited)
        check_stream_existence: Whether to check if stream exists before reading
        max_stream_check_retries: Maximum retries for checking stream existence (default: 30)
        max_read_retries: Maximum retries for reading from stream (default: 1000)

    Yields:
        tuple[str, dict[str, str]]: (message_id, message_data) from the stream

    Example:
        async for msg_id, message in listen_to_u2a_msg_stream("session-123", "msg-456"):
            print(f"Message ID: {msg_id}, Content: {message}")
    """
    stream_key = f"u2a_msg_stream:{task_uuid}"
    current_id = start_id
    stream_check_count = 0
    read_count = 0

    while True:
        try:
            # Check if stream exists with retry limit
            if check_stream_existence:
                if not await CLIENT.exists(stream_key):
                    stream_check_count += 1
                    if stream_check_count >= max_stream_existence_check_retries:
                        print(f"Stream {stream_key} does not exist after {max_stream_existence_check_retries} retries")
                        return
                    await asyncio.sleep(stream_existence_check_interval)
                    continue
                stream_check_count = 0  # Reset counter when stream exists

            # Read messages from stream
            result = await CLIENT.xread(
                {stream_key: current_id},
                count=count,
                block=block_ms
            )

            if result:
                # Parse the result: [[stream_name, [[msg_id, msg_data], ...]], ...]
                stream_data = result[0][1]  # Get the list of [msg_id, msg_data] pairs

                for msg_id, msg_data in stream_data:
                    # Convert bytes to strings for string values
                    processed_data = {}
                    for key, value in msg_data.items():
                        if isinstance(value, bytes):
                            try:
                                processed_data[key.decode()] = value.decode()
                            except UnicodeDecodeError:
                                processed_data[key.decode()] = str(value)
                        else:
                            processed_data[key] = str(value)

                    # Update current_id for next iteration
                    current_id = msg_id
                    read_count = 0  # Reset read counter when message received

                    # Check for stream_end message type
                    if processed_data.get("type") == "stream_end":
                        yield (msg_id, processed_data)
                        return

                    # Yield the message ID and processed message data
                    yield (msg_id, processed_data)

            else:
                # No messages received within block time
                read_count += 1
                if read_count >= max_read_retries:
                    print(f"No messages received after {max_read_retries} read attempts")
                    return
                continue

        except Exception as e:
            # Log error and exit on any exception
            print(f"Error reading from stream {stream_key}: {e}")
            return