from __future__ import annotations

import time
from uuid import UUID

from api.redis.constants import CLIENT
from api.redis.pub_channel_name import PubChannelNames

from .event_types import SessionEventBase


async def publish_SSE_session_event(session_id: UUID, event: SessionEventBase) -> None:
    """发布会话事件到 Redis Pub/Sub 通道。"""
    channel = PubChannelNames.session_events(session_id)
    await CLIENT.publish(channel, event.model_dump_json())