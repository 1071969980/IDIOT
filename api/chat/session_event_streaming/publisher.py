from __future__ import annotations

from uuid import UUID

from api.redis.constants import CLIENT
from api.redis.pub_channel_name import PubChannelNames
from api.redis.retry import retry_on_connection_error

from .event_types import SessionEventBase


async def publish_SSE_session_event(session_id: UUID, event: SessionEventBase) -> None:
    """发布会话事件到 Redis Pub/Sub 通道。"""
    channel = PubChannelNames.session_events(session_id)
    try:
        await retry_on_connection_error(
            lambda: CLIENT.publish(channel, event.model_dump_json()),
            operation_name=f"SSE_publish:{channel}",
        )
    except Exception:
        pass  # SSE 事件仅用于 UI 更新，丢失不影响核心逻辑