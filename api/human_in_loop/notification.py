import pickle
from asyncio import Event
from hashlib import sha256
from uuid import uuid4

from pydantic import BaseModel

from api.redis import CLIENT, HIL_RedisMsg, HIL_xadd_msg_with_expired

from .context import SEND_STREAM_KEY_PREFIX, STREAM_EXPIRE_TIME
from .execption import HILMsgStreamMissingError


async def notification(msg: BaseModel,
                        stream_identifier: str,
                        timeout: int = 3600,
                        timeout_retry: int = 6,
                        cancel_event: Event = None):
    if not isinstance(msg, BaseModel):
        raise ValueError("Invalid msg type, should be pydantic.BaseModel")
    # 0. prepare
    id = sha256(stream_identifier.encode()).hexdigest()
    send_stream_key = f"{SEND_STREAM_KEY_PREFIX}:{id}"

    # 1. check redis stream exist
    send_exist = bool(await CLIENT.exists(send_stream_key))
    if not send_exist:
        raise HILMsgStreamMissingError("human in loop send stream not exist, or expired")
    
    # 2. add msg to redis stream
    pickled_msg = pickle.dumps(msg)
    msg_id = str(uuid4())

    await HIL_xadd_msg_with_expired(
        send_stream_key,
        HIL_RedisMsg(
            msg_type="Notification",
            msg=pickled_msg,
            msg_id=msg_id,
        ),
        STREAM_EXPIRE_TIME,
    )
