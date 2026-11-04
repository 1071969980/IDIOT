"""Publish HIL interaction requests and wait for user responses."""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from asyncio import Event, Task
from typing import Any
from uuid import UUID, uuid4

import logfire
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from api.app.graceful_shutdown import set_following_task_for_graceful_shutdown_timeout
from api.chat.session_streaming.constants import (
    HIL_INTERRUPT_DEFAULT_TIMEOUT_SECONDS,
    HIL_LEASE_HEARTBEAT_SECONDS,
    human_in_loop_recv_stream_key,
)
from api.chat.session_streaming.events import (
    HilInterruptRequestEvent,
    HilInterruptRequestEventPayload,
)
from api.chat.session_streaming.hil_state import (
    discard_pending,
    refresh_pending_lease,
)
from api.chat.session_streaming.writer import publish_session_stream_event
from api.redis.constants import CLIENT

from .data_model import (
    HILInterruptContent,
    HILInterruptContentAgentToolCallBody,
    HILInterruptContentAgentToolCallBodyType,
)
from .execption import HILInterruptCancelled, HILInterruptTimeout


_RECV_READ_COUNT = 100
_RECV_XREAD_BLOCK_MS = 10_000
_REDIS_RETRY_INITIAL_BACKOFF_SECONDS = 0.5
_REDIS_RETRY_MAX_BACKOFF_SECONDS = 30.0


def _decode(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


def _iter_stream_entries(stream_data: Any):
    """Normalize RESP2/RESP3 XREAD entry nesting into (entry_id, fields)."""
    for item in stream_data:
        if (
            isinstance(item, (list, tuple))
            and len(item) == 2
            and isinstance(item[0], (bytes, str))
            and isinstance(item[1], dict)
        ):
            yield item
        elif isinstance(item, (list, tuple)):
            yield from _iter_stream_entries(item)


def _extract_response(
    result: Any,
    stream_key: str,
    msg_id: str,
) -> tuple[bool, Any, str | None]:
    """Return (matched, content, last_entry_id) from an XREAD result."""
    if not result:
        return False, None, None

    stream_data = None
    if isinstance(result, dict):
        stream_data = result.get(stream_key, result.get(stream_key.encode()))
    else:
        for key, entries in result:
            if _decode(key) == stream_key:
                stream_data = entries
                break
    if stream_data is None:
        return False, None, None

    last_entry_id: str | None = None
    for entry_id, fields in _iter_stream_entries(stream_data):
        last_entry_id = _decode(entry_id)
        raw_event = fields.get(b"event", fields.get("event"))
        if raw_event is None:
            logfire.warning(
                "HIL interrupt: recv_stream entry 缺少 event 字段",
                stream_key=stream_key,
                entry_id=last_entry_id,
            )
            continue

        try:
            event = json.loads(_decode(raw_event))
        except (TypeError, ValueError):
            logfire.warning(
                "HIL interrupt: recv_stream event JSON 解析失败",
                stream_key=stream_key,
                entry_id=last_entry_id,
            )
            continue

        if not isinstance(event, dict):
            logfire.warning(
                "HIL interrupt: recv_stream event 不是 JSON 对象",
                stream_key=stream_key,
                entry_id=last_entry_id,
            )
            continue
        if event.get("msg_id") != msg_id:
            continue
        return True, event.get("content"), last_entry_id

    return False, None, last_entry_id


async def _lease_heartbeat(
    session_id: UUID,
    msg_id: str,
    interval: float,
) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            if not await refresh_pending_lease(session_id, msg_id):
                return
        except asyncio.CancelledError:
            raise
        except Exception:
            logfire.warning(
                "HIL interrupt: 刷新交互租约失败",
                session_id=str(session_id),
                msg_id=msg_id,
            )


async def _discard_pending_best_effort(session_id: UUID, msg_id: str) -> None:
    try:
        await discard_pending(session_id, msg_id)
    except Exception:
        logfire.warning(
            "HIL interrupt: 清理 pending 状态失败",
            session_id=str(session_id),
            msg_id=msg_id,
        )


async def _interrupt(
    content: HILInterruptContent,
    *,
    session_id: UUID,
    session_task_id: UUID,
    branch_name: str | None,
    timeout: float,
    cancel_event: Event | None,
    heartbeat_interval: float,
) -> str | dict | None:
    if not isinstance(content, HILInterruptContent):
        raise ValueError("Invalid content type, should be HILInterruptContent")
    if cancel_event is not None and cancel_event.is_set():
        raise HILInterruptCancelled("HIL interrupt cancelled before publish")
    if timeout <= 0:
        raise HILInterruptTimeout(f"HIL interrupt timed out after {timeout} seconds")

    msg_id = str(uuid4())
    event = HilInterruptRequestEvent(
        session_id=session_id,
        session_task_id=session_task_id,
        branch_name=branch_name,
        payload=HilInterruptRequestEventPayload(
            msg_id=msg_id,
            content=content,
        ),
    )
    try:
        await publish_session_stream_event(event)
    except Exception:
        # The writer may have applied a write before the connection failed;
        # remove any pending state that could otherwise block a retry.
        await _discard_pending_best_effort(session_id, msg_id)
        raise

    recv_stream_key = human_in_loop_recv_stream_key(session_task_id)
    heartbeat_task: Task[None] = asyncio.create_task(
        _lease_heartbeat(session_id, msg_id, heartbeat_interval),
        name=f"hil-heartbeat:{session_task_id}",
    )
    deadline = time.monotonic() + timeout
    last_id = "0"
    redis_retry_attempt = 0

    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HILInterruptTimeout(
                    f"HIL interrupt timed out after {timeout} seconds"
                )
            if cancel_event is not None and cancel_event.is_set():
                raise HILInterruptCancelled("HIL interrupt cancelled")

            recv_task = asyncio.create_task(
                CLIENT.xread(
                    {recv_stream_key: last_id},
                    count=_RECV_READ_COUNT,
                    block=_RECV_XREAD_BLOCK_MS,
                ),
                name=f"hil-recv:{session_task_id}",
            )
            timeout_task = asyncio.create_task(asyncio.sleep(remaining))
            cancel_task: Task[bool] | None = None
            if cancel_event is not None:
                cancel_task = asyncio.create_task(cancel_event.wait())

            wait_tasks: list[Task[Any]] = [recv_task, timeout_task]
            if cancel_task is not None:
                wait_tasks.append(cancel_task)

            done, pending = await asyncio.wait(
                wait_tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

            if cancel_task is not None and cancel_task in done:
                raise HILInterruptCancelled("HIL interrupt cancelled")
            if timeout_task in done:
                raise HILInterruptTimeout(
                    f"HIL interrupt timed out after {timeout} seconds"
                )

            try:
                recv_result = recv_task.result()
            except (RedisConnectionError, RedisTimeoutError) as exc:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise HILInterruptTimeout(
                        f"HIL interrupt timed out after {timeout} seconds"
                    ) from exc
                redis_retry_attempt += 1
                backoff = min(
                    _REDIS_RETRY_INITIAL_BACKOFF_SECONDS
                    * (2 ** (redis_retry_attempt - 1)),
                    _REDIS_RETRY_MAX_BACKOFF_SECONDS,
                    remaining,
                )
                logfire.warning(
                    "HIL interrupt: recv_stream 读取失败，正在重试",
                    session_id=str(session_id),
                    msg_id=msg_id,
                    attempt=redis_retry_attempt,
                    backoff_seconds=backoff,
                    error=str(exc),
                )
                await asyncio.sleep(backoff)
                continue

            redis_retry_attempt = 0
            matched, response_content, new_last_id = _extract_response(
                recv_result,
                recv_stream_key,
                msg_id,
            )
            if new_last_id is not None:
                last_id = new_last_id
            if matched:
                if new_last_id is not None:
                    try:
                        await CLIENT.xdel(recv_stream_key, new_last_id)
                    except Exception:
                        logfire.warning(
                            "HIL interrupt: 删除已消费 recv_stream entry 失败",
                            stream_key=recv_stream_key,
                            entry_id=new_last_id,
                        )
                return response_content

    except asyncio.CancelledError:
        await _discard_pending_best_effort(session_id, msg_id)
        raise HILInterruptCancelled("HIL interrupt cancelled") from None
    except (HILInterruptTimeout, HILInterruptCancelled):
        await _discard_pending_best_effort(session_id, msg_id)
        raise
    except Exception:
        await _discard_pending_best_effort(session_id, msg_id)
        raise
    finally:
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task


async def interrupt(
    content: HILInterruptContent,
    *,
    session_id: UUID,
    session_task_id: UUID,
    branch_name: str | None = None,
    timeout: float = HIL_INTERRUPT_DEFAULT_TIMEOUT_SECONDS,
    cancel_event: Event | None = None,
) -> str | dict | None:
    """Publish a HIL interrupt and wait for the matching JSON response.

    ``timeout`` is the total business deadline measured with a monotonic clock.
    The Redis lease is refreshed independently by a heartbeat task.
    """
    with set_following_task_for_graceful_shutdown_timeout(60):
        return await _interrupt(
            content,
            session_id=session_id,
            session_task_id=session_task_id,
            branch_name=branch_name,
            timeout=timeout,
            cancel_event=cancel_event,
            heartbeat_interval=HIL_LEASE_HEARTBEAT_SECONDS,
        )
