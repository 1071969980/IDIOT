
from pydantic import BaseModel
from typing import Literal
from .constants import CLIENT
from .retry import retry_on_connection_error

HIL_REDIS_MSG_TYPE = Literal[
    "HIL_interrupt_request",
    "HIL_interrupt_response",
    "Notification",
]

class HIL_RedisMsg(BaseModel):
    msg_type: HIL_REDIS_MSG_TYPE
    content: bytes
    msg_id: str


async def HIL_xadd_msg_with_expired(stream_key: str,
                                    data: HIL_RedisMsg,
                                    expired_time:int) -> None:
    async def _do_write():
        await CLIENT.xadd(stream_key, data.model_dump())
        await CLIENT.expire(stream_key, expired_time)

    await retry_on_connection_error(_do_write, operation_name=f"HIL_xadd:{stream_key}")
