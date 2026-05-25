from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import logfire
from redis.exceptions import ConnectionError as RedisConnectionError

T = TypeVar("T")


async def retry_on_connection_error(
    operation: Callable[[], Awaitable[T]],
    *,
    operation_name: str,
    max_retries: int = 3,
    initial_backoff: float = 0.5,
    max_backoff: float = 30.0,
) -> T:
    """对 Redis 写入操作在网络瞬断时进行指数退避重试。

    仅捕获 redis.exceptions.ConnectionError（TCP 连接断开），
    其他异常直接传播。

    Args:
        operation: 要执行的异步 Redis 操作（无参数 callable）。
        operation_name: 用于日志标识的操作名称。
        max_retries: 最大重试次数。
        initial_backoff: 首次退避秒数。
        max_backoff: 退避上限秒数。
    """
    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return await operation()
        except RedisConnectionError as e:
            last_exception = e
            if attempt >= max_retries:
                break
            backoff = min(initial_backoff * (2**attempt), max_backoff)
            logfire.warning(
                "Redis 连接失败，正在重试",
                operation=operation_name,
                attempt=attempt + 1,
                max_retries=max_retries,
                backoff_seconds=backoff,
                error=str(e),
            )
            await asyncio.sleep(backoff)

    logfire.error(
        "Redis 连接恢复失败，超过最大重试次数",
        operation=operation_name,
        max_retries=max_retries,
        error=str(last_exception),
    )
    raise last_exception  # type: ignore[misc]
