import json
import pickle
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, field_validator

from api.redis import CLIENT, HIL_RedisMsg, HIL_xadd_msg_with_expired

from .context import SEND_STREAM_KEY_PREFIX, STREAM_EXPIRE_TIME
from .execption import HILMsgStreamMissingError


class HILNotificationContentAgentToolCallBodyType(str, Enum):
    Info = "Info"

class HILNotificationContentAgentToolCallBody(BaseModel):
    tool_name: str
    type: HILNotificationContentAgentToolCallBodyType
    tool_exec_uuid: str
    detail: Any

    @field_validator('detail')
    @classmethod
    def validate_detail_json_serializable(cls, v):
        if isinstance(v, BaseModel):
            try:
                v = v.model_dump(mode="json")
                return v
            except Exception as e:
                raise ValueError(f"detail字段中的Pydantic模型无法序列化为JSON: {e}")

        try:
            json.dumps(v)
            return v
        except (TypeError, ValueError) as e:
            raise ValueError(f"detail字段无法序列化为JSON: {e}")

        raise ValueError(f"detail字段必须是可JSON序列化的原生Python类型或Pydantic BaseModel，当前类型: {type(v)}")

class HILNotificationContent(BaseModel):
    source: Literal["agent_tool_call"]
    body: HILNotificationContentAgentToolCallBody


async def notification(content: HILNotificationContent,
                       stream_identifier: str):
    if not isinstance(content, HILNotificationContent):
        raise ValueError("Invalid content type, should be HILNotificationContent")

    send_stream_key = f"{SEND_STREAM_KEY_PREFIX}:{stream_identifier}"

    send_exist = bool(await CLIENT.exists(send_stream_key))
    if not send_exist:
        raise HILMsgStreamMissingError("human in loop send stream not exist, or expired")

    pickled_content = pickle.dumps(content)
    msg_id = str(uuid4())

    await HIL_xadd_msg_with_expired(
        send_stream_key,
        HIL_RedisMsg(
            msg_type="Notification",
            content=pickled_content,
            msg_id=msg_id,
        ),
        STREAM_EXPIRE_TIME,
    )
