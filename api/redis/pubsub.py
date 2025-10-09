import asyncio
import json

from .constants import CLIENT


async def publish_event(channel: str) -> None:
    """
    Publish event to specified Redis channel

    Args:
        channel: Channel name
    """
    try:
        # Always publish "set_event" message
        message = json.dumps({"type": "set_event"})
        await CLIENT.publish(channel, message)
    except Exception as e:
        error_msg = f"Failed to publish event to channel '{channel}': {e}"
        raise RuntimeError(error_msg) from e


async def subscribe_to_event(channel: str, event: asyncio.Event) -> None:
    """
    Subscribe to specified Redis channel and set event when received

    Args:
        channel: Channel name
        event: AsyncIO event to set when message is received

    Raises:
        RuntimeError: Failed to subscribe or receive message
    """
    try:
        # Create subscriber
        pubsub = CLIENT.pubsub()
        await pubsub.subscribe(channel)

        # Listen for messages
        async for message in pubsub.listen():
            # Skip subscribe/unsubscribe confirmation messages
            if message["type"] in ["subscribe", "unsubscribe"]:
                continue

            # Process actual message
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    if data.get("type") == "set_event":
                        await pubsub.unsubscribe(channel)
                        event.set()
                        return
                except (json.JSONDecodeError, AttributeError):
                    continue

        # If we exit the loop without finding the event
        await pubsub.unsubscribe(channel)

    except Exception as e:
        error_msg = f"Failed to subscribe to event channel '{channel}': {e}"
        raise RuntimeError(error_msg) from e