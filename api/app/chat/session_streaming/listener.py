"""Redis Stream listener for the session-level SSE event bus."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any, AsyncGenerator
from uuid import UUID

import logfire
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError
from redis.exceptions import TimeoutError as RedisTimeoutError

from api.chat.session_streaming.constants import session_event_stream_key
from api.chat.session_streaming.events import (
    HilInterruptRequestEvent,
    HilNotificationEvent,
    SessionStreamEvent,
    SessionStreamEventAdapter,
)
from api.chat.session_streaming.hil_state import read_pending_interaction
from api.redis.constants import CLIENT


_READ_COUNT = 100
_READ_BLOCK_MS = 10_000
_MAX_BACKOFF_SECONDS = 30.0


class SessionListenerControl(str, Enum):
    CURSOR_EXPIRED = "cursor_expired"


@dataclass(frozen=True)
class SessionStreamRecord:
    entry_id: str
    raw_json: str
    event: SessionStreamEvent


SessionListenerItem = SessionStreamRecord | SessionListenerControl


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


def _extract_entries(result: Any, stream_key: str) -> list[tuple[str, dict]]:
    if not result:
        return []

    stream_data = None
    if isinstance(result, dict):
        stream_data = result.get(stream_key, result.get(stream_key.encode()))
    else:
        for key, entries in result:
            if _decode(key) == stream_key:
                stream_data = entries
                break

    if stream_data is None:
        return []
    return [
        (_decode(entry_id), fields)
        for entry_id, fields in _iter_stream_entries(stream_data)
    ]


def _stream_id_key(value: str) -> tuple[int, int]:
    milliseconds, sequence = value.split("-", 1)
    return int(milliseconds), int(sequence)


def _cursor_is_older(cursor: str, earliest_id: str) -> bool:
    try:
        return _stream_id_key(cursor) < _stream_id_key(earliest_id)
    except (TypeError, ValueError):
        return False


async def _detect_cursor_expired(
    stream_key: str,
    cursor: str,
) -> bool:
    if cursor == "0":
        return False
    earliest_entries = await CLIENT.xrange(stream_key, min="-", max="+", count=1)
    if not earliest_entries:
        return False
    earliest_id = _decode(earliest_entries[0][0])
    return _cursor_is_older(cursor, earliest_id)


async def _is_hil_event_visible(session_id: UUID, event: SessionStreamEvent) -> bool:
    if isinstance(event, (HilInterruptRequestEvent, HilNotificationEvent)):
        return await read_pending_interaction(session_id, event.payload.msg_id)
    return True


async def session_event_listener(
    session_id: UUID,
    start_id: str = "0",
) -> AsyncGenerator[SessionListenerItem, None]:
    """Continuously consume one session's Redis Stream.

    The cursor advances after an entry is parsed and either fails parsing (and
    is skipped) or successfully passes HIL visibility filtering. Redis errors
    while checking HIL state are propagated so the outer retry loop keeps the
    cursor unchanged. Business ``stream_end`` entries never terminate the
    subscription.
    """
    stream_key = session_event_stream_key(session_id)
    cursor = start_id
    retry_attempt = 0
    total_events = 0

    logfire.info(
        "session_event_listener: 开始监听",
        stream_key=stream_key,
        start_id=start_id,
    )
    try:
        while True:
            try:
                result = await CLIENT.xread(
                    {stream_key: cursor},
                    count=_READ_COUNT,
                    block=_READ_BLOCK_MS,
                )
                retry_attempt = 0

                # Check on every read, not only at connect time, so an expired,
                # rebuilt, or trimmed stream can be reported while connected.
                if await _detect_cursor_expired(stream_key, cursor):
                    logfire.warning(
                        "session_event_listener: 游标已早于当前保留窗口",
                        stream_key=stream_key,
                        cursor=cursor,
                    )
                    yield SessionListenerControl.CURSOR_EXPIRED
                    # XREAD is exclusive; replay from the earliest retained
                    # event after reporting the gap.
                    cursor = "0"
                    continue

                for entry_id, fields in _extract_entries(result, stream_key):
                    raw_event = fields.get(b"event", fields.get("event"))
                    if raw_event is None:
                        logfire.warning(
                            "session_event_listener: entry 缺少 event 字段，跳过",
                            stream_key=stream_key,
                            entry_id=entry_id,
                        )
                        cursor = entry_id
                        continue

                    raw_json = _decode(raw_event)
                    try:
                        event = SessionStreamEventAdapter.validate_json(raw_json)
                    except Exception:
                        logfire.warning(
                            "session_event_listener: 事件反序列化失败，跳过",
                            stream_key=stream_key,
                            entry_id=entry_id,
                        )
                        cursor = entry_id
                        continue

                    # Keep the cursor unchanged for any state-check failure.
                    # The outer loop retries transient Redis errors and closes
                    # the connection on deterministic/unexpected failures.
                    visible = await _is_hil_event_visible(session_id, event)

                    if not visible:
                        cursor = entry_id
                        continue

                    cursor = entry_id
                    total_events += 1
                    yield SessionStreamRecord(
                        entry_id=entry_id,
                        raw_json=raw_json,
                        event=event,
                    )

            except asyncio.CancelledError:
                raise
            except (RedisConnectionError, RedisTimeoutError) as exc:
                retry_attempt += 1
                backoff = min(2 ** (retry_attempt - 1), _MAX_BACKOFF_SECONDS)
                logfire.warning(
                    "session_event_listener: Redis 连接中断，正在重试",
                    stream_key=stream_key,
                    cursor=cursor,
                    attempt=retry_attempt,
                    backoff_seconds=backoff,
                    error=str(exc),
                )
                await asyncio.sleep(backoff)
            except RedisError as exc:
                logfire.error(
                    "session_event_listener: 非瞬态 Redis 错误，关闭连接",
                    stream_key=stream_key,
                    cursor=cursor,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                raise
            except Exception as exc:
                logfire.error(
                    "session_event_listener: 未预期异常，关闭连接",
                    stream_key=stream_key,
                    cursor=cursor,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                raise
    finally:
        logfire.info(
            "session_event_listener: 连接关闭",
            stream_key=stream_key,
            cursor=cursor,
            total_events=total_events,
        )
