import asyncio
import pickle
from typing import Any, AsyncGenerator
from uuid import UUID

import logfire
from pydantic import BaseModel
from redis.exceptions import ConnectionError as RedisConnectionError

from api.redis import CLIENT

from ..context import SEND_STREAM_KEY_PREFIX


async def hil_msg_stream_generator(
    task_id: UUID,
    start_id: str = "0",
    block_ms: int = 10000,
    check_stream_existence: bool = True,
    stream_existence_check_interval: int = 1,
    max_stream_existence_check_retries: int = 10,
    max_read_retries: int = 1000,
) -> AsyncGenerator[tuple[str, dict[str, Any]], None]:
    """
    从 HIL send stream 读取消息并 yield 出去。
    HIL stream 没有 stream_end 信号，依赖空读超限退出。
    """
    stream_key = f"{SEND_STREAM_KEY_PREFIX}:{task_id}"
    current_id = start_id
    stream_check_count = 0
    read_count = 0
    connection_retry_count = 0
    max_connection_retries = 5

    with logfire.span(
        "api/human_in_loop/http_worker/stream_listener.py::hil_msg_stream_generator",
        stream_key=stream_key,
        start_id=start_id,
    ):
        while True:
            try:
                if check_stream_existence:
                    if not await CLIENT.exists(stream_key):
                        stream_check_count += 1
                        if stream_check_count >= max_stream_existence_check_retries:
                            logfire.warning(
                                "HIL stream_listener: stream 不存在，超过最大重试次数",
                                stream_key=stream_key,
                                retries=stream_check_count,
                            )
                            return
                        await asyncio.sleep(stream_existence_check_interval)
                        continue
                    stream_check_count = 0

                result = await CLIENT.xread(
                    {stream_key: current_id},
                    count=1,
                    block=block_ms,
                )

                if result:
                    stream_data = result[stream_key.encode()][0]
                    for msg_id, msg_data in stream_data:
                        redis_msg_id = msg_id.decode()
                        msg_type = msg_data[b"msg_type"].decode()
                        msg_id_str = msg_data[b"msg_id"].decode()

                        # stream_end 信号：content 为空字符串，不需要 pickle 反序列化
                        if msg_type == "stream_end":
                            logfire.info(
                                "HIL stream_listener: 收到 stream_end，正常结束",
                                stream_key=stream_key,
                                last_msg_id=msg_id_str,
                            )
                            return

                        try:
                            msg_content = pickle.loads(msg_data[b"content"])
                            if isinstance(msg_content, BaseModel):
                                msg_content = msg_content.model_dump(mode="json")
                        except Exception as e:
                            logfire.warning(
                                "HIL stream_listener: 消息反序列化失败，跳过",
                                stream_key=stream_key,
                                redis_msg_id=redis_msg_id,
                                error=str(e),
                            )
                            current_id = msg_id
                            continue

                        current_id = msg_id
                        read_count = 0

                        yield (redis_msg_id, {
                            "msg_id": msg_id_str,
                            "msg_type": msg_type,
                            "content": msg_content,
                        })
                else:
                    read_count += 1
                    if read_count >= max_read_retries:
                        logfire.warning(
                            "HIL stream_listener: 连续空读超过上限",
                            stream_key=stream_key,
                            read_count=read_count,
                        )
                        return
                    continue

            except RedisConnectionError as e:
                connection_retry_count += 1
                if connection_retry_count >= max_connection_retries:
                    logfire.error(
                        "HIL stream_listener: Redis 连接恢复失败，超过最大重试次数",
                        stream_key=stream_key,
                        retries=connection_retry_count,
                        error=str(e),
                    )
                    return
                logfire.warning(
                    "HIL stream_listener: Redis 连接中断，正在重试",
                    stream_key=stream_key,
                    retry=connection_retry_count,
                    error=str(e),
                )
                await asyncio.sleep(min(2 ** connection_retry_count, 30))
                continue

            except Exception as e:
                logfire.error(
                    "HIL stream_listener: 未预期的异常",
                    stream_key=stream_key,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                return
