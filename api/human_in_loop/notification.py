import pickle
from uuid import uuid4


from api.redis import CLIENT, HIL_RedisMsg, HIL_xadd_msg_with_expired

from .context import SEND_STREAM_KEY_PREFIX, STREAM_EXPIRE_TIME
from .execption import HILMsgStreamMissingError


from .data_model import (
    HILNotificationContent,
    HILNotificationContentAgentToolCallBody,
    HILNotificationContentAgentToolCallBodyType,
)


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
