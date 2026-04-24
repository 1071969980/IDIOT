import asyncio
import json
import time
from typing import AsyncGenerator
from uuid import UUID

import logfire
from redis.exceptions import ConnectionError as RedisConnectionError

from api.redis.constants import CLIENT
from api.redis.event_names import EventNames


async def session_event_listener(
    session_id: UUID,
    heartbeat_interval: float = 15.0,
    max_connection_retries: int = 5,
) -> AsyncGenerator[tuple[str, dict, str], None]:
    """
    监听 Redis Pub/Sub 通道并 yield 事件。

    无消息时按 heartbeat_interval 发送心跳事件。
    Redis 连接中断时指数退避重试。

    Yields:
        (event_type, data_dict, event_id_counter)
    """
    channel = EventNames.session_events(session_id)
    event_counter = 0
    connection_retry_count = 0

    with logfire.span(
        "api/app/chat/session_event_streaming/listener.py::session_event_listener",
        channel=channel,
    ):
        pubsub = CLIENT.pubsub()
        try:
            await pubsub.subscribe(channel)

            while True:
                try:
                    aiter = pubsub.listen().__aiter__()
                    while True:
                        try:
                            message = await asyncio.wait_for(
                                aiter.__anext__(),
                                timeout=heartbeat_interval,
                            )
                        except asyncio.TimeoutError:
                            event_counter += 1
                            yield (
                                "heartbeat",
                                {"timestamp": time.time()},
                                str(event_counter),
                            )
                            continue
                        except StopAsyncIteration:
                            return

                        if message["type"] in ("subscribe", "unsubscribe"):
                            continue

                        if message["type"] == "message":
                            try:
                                data = json.loads(message["data"])
                                event_counter += 1
                                yield (
                                    data.get("event_type", "unknown"),
                                    data,
                                    str(event_counter),
                                )
                            except (json.JSONDecodeError, AttributeError):
                                continue

                except RedisConnectionError as e:
                    connection_retry_count += 1
                    if connection_retry_count >= max_connection_retries:
                        logfire.error(
                            "session_event_listener: Redis 连接恢复失败，超过最大重试次数",
                            channel=channel,
                            retries=connection_retry_count,
                            error=str(e),
                        )
                        return

                    logfire.warning(
                        "session_event_listener: Redis 连接中断，正在重试",
                        channel=channel,
                        retry=connection_retry_count,
                        error=str(e),
                    )
                    await asyncio.sleep(min(2**connection_retry_count, 30))

                    # 重建 pubsub 连接
                    try:
                        await pubsub.aclose()
                    except Exception:
                        pass
                    pubsub = CLIENT.pubsub()
                    await pubsub.subscribe(channel)
                    continue

                except Exception as e:
                    logfire.error(
                        "session_event_listener: 未预期的异常",
                        channel=channel,
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    return
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()
            except Exception:
                pass

            logfire.info(
                "session_event_listener: 连接关闭",
                channel=channel,
                total_events=event_counter,
            )
