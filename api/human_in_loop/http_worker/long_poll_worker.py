"""
HIL Worker 响应处理
提供 send_response 和 ack_message 功能（SSE 端点不再需要 poll 逻辑）
"""

import pickle

from fastapi import HTTPException
from loguru import logger

from api.redis import CLIENT, HIL_RedisMsg, HIL_xadd_msg_with_expired
from ..context import SEND_STREAM_KEY_PREFIX, RECV_STREAM_KEY_PREFIX, STREAM_EXPIRE_TIME


class LongPollWorker:

    async def send_response_with_params(self, msg_id: str, msg: str | dict, stream_identifier: str, user_identifier: str):
        """发送用户响应"""

        recv_stream_key = f"{RECV_STREAM_KEY_PREFIX}:{stream_identifier}"

        if not await CLIENT.exists(recv_stream_key):
            raise HTTPException(status_code=404, detail="Stream not found or expired")

        pickled_msg = pickle.dumps(msg)

        await HIL_xadd_msg_with_expired(
            recv_stream_key,
            HIL_RedisMsg(
                msg_type="HIL_interrupt_response",
                content=pickled_msg,
                msg_id=msg_id,
            ),
            STREAM_EXPIRE_TIME,
        )

    async def ack_message(self, HIL_msg_id: str, stream_identifier: str, user_identifier: str) -> bool:
        """确认消息接收并删除"""

        send_stream_key = f"{SEND_STREAM_KEY_PREFIX}:{stream_identifier}"

        try:
            result = await CLIENT.xread({send_stream_key: "0"}, count=None)

            if not result:
                raise HTTPException(status_code=404, detail="Stream not found or expired")

            for redis_msg_id, msg_data in result[send_stream_key.encode()][0]:
                msg_id_str = msg_data[b"msg_id"].decode()

                if msg_id_str == HIL_msg_id:
                    await CLIENT.xdel(send_stream_key, redis_msg_id)
                    logger.info(f"Deleted message {HIL_msg_id} from stream {stream_identifier}")
                    # TODO: Serialize msg to postgres
                    return True

            raise HTTPException(status_code=404, detail="Message not found")

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to ack message: {e}")
            raise HTTPException(status_code=500, detail="Failed to acknowledge message")


long_poll_worker = LongPollWorker()
