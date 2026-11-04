"""HIL interaction state and recv-stream Redis operations.

All state transitions are implemented as single Redis Lua scripts so that a
status change and the corresponding recv-stream write cannot produce a
half-applied intermediate state.
"""

from __future__ import annotations

import json
from enum import Enum
from uuid import UUID

from api.redis.constants import CLIENT

from .constants import (
    HIL_INTERACTION_LEASE_MS,
    HIL_INTERACTION_STATE_TTL_SECONDS,
    SESSION_EVENT_STREAM_MAXLEN,
    SESSION_EVENT_STREAM_TTL_SECONDS,
    hil_interaction_state_key,
    human_in_loop_recv_stream_key,
    session_event_stream_key,
)


class TransitionResult(str, Enum):
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"


_PUBLISH_PENDING_LUA = """
local t = redis.call('TIME')
local now_ms = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local existing = redis.call('HGET', KEYS[2], ARGV[2])
local pending_json = false
if not existing then
    local expires_at = now_ms + tonumber(ARGV[3])
    pending_json = '{"state":"pending","expires_at":' .. string.format('%.0f', expires_at) .. '}'
else
    local ok, state = pcall(cjson.decode, existing)
    if ok and type(state) == 'table' and state.state == 'pending' then
        local expires_at = now_ms + tonumber(ARGV[3])
        pending_json = '{"state":"pending","expires_at":' .. string.format('%.0f', expires_at) .. '}'
    end
end
local stream_id = redis.call(
    'XADD', KEYS[1], 'MAXLEN', '~', ARGV[6], '*', 'event', ARGV[1]
)
if pending_json then
    redis.call('HSET', KEYS[2], ARGV[2], pending_json)
end
redis.call('EXPIRE', KEYS[1], ARGV[4])
redis.call('EXPIRE', KEYS[2], ARGV[5])
return stream_id
"""

_READ_PENDING_LUA = """
local raw = redis.call('HGET', KEYS[1], ARGV[1])
if not raw then
    return 0
end
local ok, state = pcall(cjson.decode, raw)
if not ok or type(state) ~= 'table' or state.state ~= 'pending' then
    return 0
end
local t = redis.call('TIME')
local now_ms = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local expires_at = tonumber(state.expires_at)
if not expires_at or expires_at <= now_ms then
    redis.call('HDEL', KEYS[1], ARGV[1])
    return 0
end
return 1
"""

_REFRESH_PENDING_LUA = """
local raw = redis.call('HGET', KEYS[2], ARGV[1])
if not raw then
    return 0
end
local ok, state = pcall(cjson.decode, raw)
if not ok or type(state) ~= 'table' or state.state ~= 'pending' then
    return 0
end
local t = redis.call('TIME')
local now_ms = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local expires_at = tonumber(state.expires_at)
if not expires_at or expires_at <= now_ms then
    redis.call('HDEL', KEYS[2], ARGV[1])
    return 0
end
local new_expires_at = now_ms + tonumber(ARGV[2])
local pending_json = '{"state":"pending","expires_at":' .. string.format('%.0f', new_expires_at) .. '}'
redis.call('HSET', KEYS[2], ARGV[1], pending_json)
redis.call('EXPIRE', KEYS[1], ARGV[3])
redis.call('EXPIRE', KEYS[2], ARGV[4])
return 1
"""

_TRANSITION_RESPONDED_LUA = """
local raw = redis.call('HGET', KEYS[1], ARGV[1])
if not raw then
    return 'not_found'
end
local ok, state = pcall(cjson.decode, raw)
if not ok or type(state) ~= 'table' then
    redis.call('HDEL', KEYS[1], ARGV[1])
    return 'not_found'
end
local t = redis.call('TIME')
local now_ms = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local expires_at = tonumber(state.expires_at)
if not expires_at or expires_at <= now_ms then
    redis.call('HDEL', KEYS[1], ARGV[1])
    return 'not_found'
end
if state.state ~= 'pending' then
    return 'conflict'
end
redis.call('XADD', KEYS[2], '*', 'event', ARGV[2])
local new_expires_at = now_ms + tonumber(ARGV[3])
local responded_json = '{"state":"responded","expires_at":' .. string.format('%.0f', new_expires_at) .. '}'
redis.call('HSET', KEYS[1], ARGV[1], responded_json)
redis.call('EXPIRE', KEYS[1], ARGV[4])
redis.call('EXPIRE', KEYS[2], ARGV[5])
return 'success'
"""

_TRANSITION_ACKED_LUA = """
local raw = redis.call('HGET', KEYS[1], ARGV[1])
if not raw then
    return 'not_found'
end
local ok, state = pcall(cjson.decode, raw)
if not ok or type(state) ~= 'table' then
    redis.call('HDEL', KEYS[1], ARGV[1])
    return 'not_found'
end
local t = redis.call('TIME')
local now_ms = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local expires_at = tonumber(state.expires_at)
if not expires_at or expires_at <= now_ms then
    redis.call('HDEL', KEYS[1], ARGV[1])
    return 'not_found'
end
if state.state ~= 'pending' then
    return 'conflict'
end
local new_expires_at = now_ms + tonumber(ARGV[2])
local acked_json = '{"state":"acked","expires_at":' .. string.format('%.0f', new_expires_at) .. '}'
redis.call('HSET', KEYS[1], ARGV[1], acked_json)
redis.call('EXPIRE', KEYS[1], ARGV[3])
return 'success'
"""

_DISCARD_PENDING_LUA = """
local raw = redis.call('HGET', KEYS[1], ARGV[1])
if not raw then
    return 0
end
local ok, state = pcall(cjson.decode, raw)
if not ok or type(state) ~= 'table' or state.state ~= 'pending' then
    return 0
end
redis.call('HDEL', KEYS[1], ARGV[1])
return 1
"""


def _as_str(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


def _build_recv_event_json(msg_id: str, response_json: str) -> str:
    """Wrap serialized response content into the recv-stream event envelope."""
    response_content = json.loads(response_json)
    return json.dumps(
        {"msg_id": msg_id, "content": response_content},
        ensure_ascii=False,
        separators=(",", ":"),
    )


async def publish_pending_interaction_event(
    session_id: UUID,
    msg_id: str,
    event_json: str,
) -> str:
    """Atomically append a HIL event and register its pending interaction."""
    stream_id = await CLIENT.eval(
        _PUBLISH_PENDING_LUA,
        2,
        session_event_stream_key(session_id),
        hil_interaction_state_key(session_id),
        event_json,
        msg_id,
        str(HIL_INTERACTION_LEASE_MS),
        str(SESSION_EVENT_STREAM_TTL_SECONDS),
        str(HIL_INTERACTION_STATE_TTL_SECONDS),
        str(SESSION_EVENT_STREAM_MAXLEN),
    )
    return _as_str(stream_id)


async def read_pending_interaction(session_id: UUID, msg_id: str) -> bool:
    """Return whether an interaction is still pending and unexpired.

    P4 should use this API for both live and replayed HIL events instead of
    interpreting the state hash itself. Expired fields are removed by the Lua
    script using Redis time.
    """
    pending = await CLIENT.eval(
        _READ_PENDING_LUA,
        1,
        hil_interaction_state_key(session_id),
        msg_id,
    )
    return bool(int(pending))


async def refresh_pending_lease(session_id: UUID, msg_id: str) -> bool:
    """Refresh the stream/state TTLs and lease while an interaction is pending."""
    refreshed = await CLIENT.eval(
        _REFRESH_PENDING_LUA,
        2,
        session_event_stream_key(session_id),
        hil_interaction_state_key(session_id),
        msg_id,
        str(HIL_INTERACTION_LEASE_MS),
        str(SESSION_EVENT_STREAM_TTL_SECONDS),
        str(HIL_INTERACTION_STATE_TTL_SECONDS),
    )
    return bool(int(refreshed))


async def transition_to_responded(
    session_id: UUID,
    session_task_id: UUID,
    msg_id: str,
    response_json: str,
) -> TransitionResult:
    """Atomically mark a pending interaction responded and write its response.

    ``response_json`` is the serialized response content. It is wrapped into
    ``{"msg_id": ..., "content": ...}`` for the recv stream.
    """
    recv_event_json = _build_recv_event_json(msg_id, response_json)
    result = await CLIENT.eval(
        _TRANSITION_RESPONDED_LUA,
        2,
        hil_interaction_state_key(session_id),
        human_in_loop_recv_stream_key(session_task_id),
        msg_id,
        recv_event_json,
        str(HIL_INTERACTION_LEASE_MS),
        str(HIL_INTERACTION_STATE_TTL_SECONDS),
        str(HIL_INTERACTION_STATE_TTL_SECONDS),
    )
    return TransitionResult(_as_str(result))


async def transition_to_acked(session_id: UUID, msg_id: str) -> TransitionResult:
    """Atomically mark a pending notification interaction as acknowledged."""
    result = await CLIENT.eval(
        _TRANSITION_ACKED_LUA,
        1,
        hil_interaction_state_key(session_id),
        msg_id,
        str(HIL_INTERACTION_LEASE_MS),
        str(HIL_INTERACTION_STATE_TTL_SECONDS),
    )
    return TransitionResult(_as_str(result))


async def discard_pending(session_id: UUID, msg_id: str) -> bool:
    """Best-effort removal of a pending interaction before timeout/cancel."""
    discarded = await CLIENT.eval(
        _DISCARD_PENDING_LUA,
        1,
        hil_interaction_state_key(session_id),
        msg_id,
    )
    return bool(int(discarded))
