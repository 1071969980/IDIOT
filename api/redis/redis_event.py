import asyncio
import json
from contextlib import suppress

from .constants import CLIENT


class RedisEvent:
    """
    基于 Redis Pub/Sub 的分布式事件，对外接口类似 asyncio.Event。

    支持跨进程的事件通知：一个进程 set()，另一个进程 wait() 会被唤醒。

    用法:
        # 进程 A - 等待事件
        event = RedisEvent("my_event")
        await event.wait()  # 阻塞直到事件被设置

        # 进程 B - 触发事件
        event = RedisEvent("my_event")
        await event.set()

        # 带超时等待
        event = RedisEvent("my_event")
        try:
            await event.wait(timeout=30)
        except asyncio.TimeoutError:
            print("Timed out")

        # 访问本地 asyncio.Event
        event.local_event.set()
    """

    def __init__(self, channel: str) -> None:
        self._channel = channel
        self._local_event = asyncio.Event()

    async def set(self) -> None:
        """发布事件到 Redis channel，通知所有订阅者。"""
        message = json.dumps({"type": "set_event"})
        try:
            await CLIENT.publish(self._channel, message)
        except Exception as e:
            raise RuntimeError(
                f"Failed to publish event to channel '{self._channel}': {e}"
            ) from e
        self._local_event.set()

    async def wait(self, timeout: float | None = None) -> None:
        """
        等待事件被设置。如果本地已经被设置则立即返回，否则订阅 Redis channel 等待。

        Args:
            timeout: 超时秒数，None 表示无限等待。超时抛出 asyncio.TimeoutError。

        Raises:
            asyncio.TimeoutError: 超时未收到事件
        """
        if self._local_event.is_set():
            return

        subscribe_task = asyncio.create_task(
            _subscribe_and_set(self._channel, self._local_event)
        )
        try:
            await asyncio.wait_for(asyncio.shield(subscribe_task), timeout=timeout)
        except TimeoutError:
            raise asyncio.TimeoutError(
                f"RedisEvent '{self._channel}' timed out after {timeout}s"
            )
        finally:
            subscribe_task.cancel()
            with suppress(asyncio.CancelledError):
                await subscribe_task

    @property
    def local_event(self) -> asyncio.Event:
        """返回本地 asyncio.Event 实例，用于与 asyncio 原生 API 协作。"""
        return self._local_event

    def is_set(self) -> bool:
        """返回事件是否已被设置（仅本地状态）。"""
        return self._local_event.is_set()

    def clear(self) -> None:
        """重置本地事件状态。"""
        self._local_event.clear()


async def _subscribe_and_set(channel: str, event: asyncio.Event) -> None:
    """订阅 Redis channel，收到 set_event 消息后设置本地 event。"""
    pubsub = CLIENT.pubsub()
    async with pubsub:
        await pubsub.subscribe(channel)
        async for message in pubsub.listen():
            if message["type"] in ("subscribe", "unsubscribe"):
                continue
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    if data.get("type") == "set_event":
                        event.set()
                        return
                except (json.JSONDecodeError, AttributeError):
                    continue


# ---- 遗留函数（保持向后兼容） ----


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
    Subscribe to specified Redis channel and set event when received.

    **Important**: This function runs indefinitely until a message is received.
    It should be run as a background task to avoid blocking the main execution:

    ```python
    # Create a background task for subscription
    subscribe_task = asyncio.create_task(subscribe_to_event(channel, event))

    # Wait for the event with timeout
    try:
        await asyncio.wait_for(event.wait(), timeout=30)
    finally:
        # Always cancel the subscription task when done
        subscribe_task.cancel()
        try:
            await subscribe_task
        except asyncio.CancelledError:
            pass
    ```

    Args:
        channel: Channel name
        event: AsyncIO event to set when message is received

    Raises:
        RuntimeError: Failed to subscribe or receive message
    """
    try:
        # Create subscriber
        pubsub = CLIENT.pubsub()
        async with pubsub:
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
