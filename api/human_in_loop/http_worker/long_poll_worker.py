"""
HTTP Worker长轮询端点
实现消息轮询和响应处理
"""

import asyncio
import pickle
import time
from typing import Any
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel
from api.redis import CLIENT
from ..context import SEND_STREAM_KEY_PREFIX, RECV_STREAM_KEY_PREFIX, STREAM_EXPIRE_TIME
from .data_model import HILPollResponse


class SimpleResponse:
    """简单的响应模型"""
    def __init__(self, status: str, message: str, msg_id: str):
        self.status = status
        self.message = message
        self.msg_id = msg_id


class LongPollWorker:
    """长轮询工作者"""
    
    def __init__(self):
        self.timeout = 30  # 默认超时时间
    
    async def poll_messages(self, stream_identifier: str, last_id: str = "0", timeout: int = 30) -> HILPollResponse:
        """轮询消息"""
        
        # 检查Redis流是否存在
        send_stream_key = f"{SEND_STREAM_KEY_PREFIX}:{stream_identifier}"
        if not await CLIENT.exists(send_stream_key):
            raise HTTPException(status_code=204, detail="Stream not found or expired")
        
        # 长轮询获取消息
        redis_last_id ,HIL_message = await self._read_messages_from_stream(
            stream_identifier, 
            last_id, 
            timeout
        )
        
        # 构建JsonRPC请求格式，参考WebSocket worker的forwarding_send_stream
        return HILPollResponse(
                redis_last_id=redis_last_id,
                HIL_msg=HIL_message,
            )
    
    async def send_response_with_params(self, msg_id: str, msg: str | dict, stream_identifier: str, user_identifier: str):
        """发送用户响应（参数版本）"""
        
        # 写入Redis流
        recv_stream_key = f"{RECV_STREAM_KEY_PREFIX}:{stream_identifier}"
        
        # 检查Redis流是否存在
        if not await CLIENT.exists(recv_stream_key):
            raise HTTPException(status_code=404, detail="Stream not found or expired")
        

        # 序列化消息
        pickled_msg = pickle.dumps(msg)
        
        # 使用现有的HIL_xadd_msg_with_expired函数格式
        from api.redis import HIL_RedisMsg, HIL_xadd_msg_with_expired
        
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
            # 读取流中的所有消息，查找匹配的msg_id
            result = await CLIENT.xread({send_stream_key: "0"}, count=None)
            
            if not result:
                raise HTTPException(status_code=404, detail="Stream not found or expired")
            
            # 遍历消息查找匹配的msg_id
            for redis_msg_id, msg_data in result[send_stream_key.encode()][0]: # result[0][0] is stream key
                msg_id_str = msg_data[b"msg_id"].decode()
                
                if msg_id_str == HIL_msg_id:
                    # 找到匹配的消息，删除它
                    await CLIENT.xdel(send_stream_key, redis_msg_id)
                    logger.info(f"Deleted message {HIL_msg_id} from stream {stream_identifier}")
                    # TODO: Serialize msg to postgres
                    
                    return True
            
            # 没有找到匹配的消息
            raise HTTPException(status_code=404, detail="Message not found")
        
        except HTTPException as e:
            raise
        except Exception as e:
            logger.error(f"Failed to ack message: {e}")
            raise HTTPException(status_code=500, detail="Failed to acknowledge message")
    
    async def _read_messages_from_stream(self, 
                                         stream_identifier: str, 
                                         last_id: str, 
                                         timeout: int) -> tuple[str, dict[str, Any] | None]:
        """从Redis流读取消息（只读取一个消息）"""
        send_stream_key = f"{SEND_STREAM_KEY_PREFIX}:{stream_identifier}"
        
        # 如果没有指定last_id，从开头读取
        start_id = last_id if last_id else "0"
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # 阻塞读取消息，只读取一个
                result = await CLIENT.xread(
                    {send_stream_key: start_id},
                    count=1,  # 只读取一个消息
                    block=min(1000, timeout * 1000)  # 毫秒
                )
                
                if result:
                    # 解析消息
                    stream_data = result[send_stream_key.encode()][0]
                    redis_msg_id, msg_data = stream_data[0]  # 只取第一个消息
                    redis_msg_id = redis_msg_id.decode()
                    try:
                        msg_type = msg_data[b"msg_type"].decode()
                        msg_content = pickle.loads(msg_data[b"content"])
                        if isinstance(msg_content, BaseModel):
                            msg_content = msg_content.model_dump(mode="json")
                        msg_id_str = msg_data[b"msg_id"].decode()
                        
                        # 返回单个消息, Same as api/redis/human_in_loop.py::HIL_RedisMsg, but decoded from bytes
                        return redis_msg_id, {
                            "msg_id": msg_id_str,
                            "msg_type": msg_type,
                            "content": msg_content,
                        }
                        
                    except Exception as e:
                        logger.error(f"Failed to parse message: {e}")
                        continue
                
                # 没有消息，短暂等待后继续
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error reading from stream: {e}")
                break
        
        return last_id, None


# 全局长轮询工作者实例
long_poll_worker = LongPollWorker()