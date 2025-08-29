"""
HTTP Worker长轮询端点
实现消息轮询和响应处理
"""

import asyncio
import pickle
import time
from typing import Any
from fastapi import HTTPException, BackgroundTasks
from loguru import logger
from api.redis import CLIENT
from ..context import SEND_STREAM_KEY_PREFIX, RECV_STREAM_KEY_PREFIX, STREAM_EXPIRE_TIME
from .data_model import HTTPPollRequest, HTTPJsonRPCRequest, HTTPJsonRPCResponse, HTTPJsonRPCError, generate_request_id


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
        self.heartbeat_interval = 5  # 心跳间隔
    
    
    async def poll_messages(self, request: HTTPPollRequest, stream_identifier: str, user_identifier: str) -> HTTPJsonRPCRequest | None:
        """轮询消息"""
        
        # 检查Redis流是否存在
        send_stream_key = f"{SEND_STREAM_KEY_PREFIX}:{stream_identifier}"
        if not await CLIENT.exists(send_stream_key):
            raise HTTPException(status_code=404, detail="Stream not found or expired")
        
        # 长轮询获取消息，总是从"0"开始读取
        message = await self._read_messages_from_stream(
            stream_identifier, 
            "0", 
            request.timeout
        )
        
        # 构建JsonRPC请求格式，参考WebSocket worker的forwarding_send_stream
        if message:
            request_id = generate_request_id()
            return HTTPJsonRPCRequest(
                id=request_id,
                method=message["msg_type"],
                params={
                    "msg_id": message["msg_id"],
                    "msg": message["msg"],
                }
            )
        else:
            # 无消息时返回None表示没有消息
            return None
    
    async def send_response_with_params(self, msg_id: str, msg: Any, stream_identifier: str, user_identifier: str) -> SimpleResponse:
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
                msg=pickled_msg,
                msg_id=msg_id,
            ),
            STREAM_EXPIRE_TIME,
        )
        
        logger.info(f"Sent response for stream {stream_identifier}, msg_id: {msg_id}")
        
        return SimpleResponse(
            status="success",
            message="Response sent successfully",
            msg_id=msg_id
        )
    
    async def ack_message(self, msg_id: str, stream_identifier: str, user_identifier: str) -> bool:
        """确认消息接收并删除"""
        
        send_stream_key = f"{SEND_STREAM_KEY_PREFIX}:{stream_identifier}"
        
        try:
            # 读取流中的所有消息，查找匹配的msg_id
            result = await CLIENT.xread({send_stream_key: "0"}, count=None)
            
            if not result:
                return False
            
            # 遍历消息查找匹配的msg_id
            for stream_data in result:
                for redis_msg_id, msg_data in stream_data[1]:
                    try:
                        msg_id_str = msg_data[b"msg_id"].decode()
                        
                        if msg_id_str == msg_id:
                            # 找到匹配的消息，删除它
                            await CLIENT.xdel(send_stream_key, redis_msg_id)
                            logger.info(f"Deleted message {msg_id} from stream {stream_identifier}")
                            return True
                    except Exception as e:
                        logger.error(f"Error parsing message {redis_msg_id}: {e}")
                        continue
            
            # 没有找到匹配的消息
            return False
            
        except Exception as e:
            logger.error(f"Failed to ack message: {e}")
            raise HTTPException(status_code=500, detail="Failed to acknowledge message")
    
    async def _read_messages_from_stream(self, stream_identifier: str, last_id: str, timeout: int) -> dict[str, Any] | None:
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
                    stream_data = result[0][1]
                    redis_msg_id, msg_data = stream_data[0]  # 只取第一个消息
                    
                    try:
                        msg_type = msg_data[b"msg_type"].decode()
                        msg_content = pickle.loads(msg_data[b"msg"])
                        msg_id_str = msg_data[b"msg_id"].decode()
                        
                        # 返回单个消息
                        return {
                            "msg_id": msg_id_str,
                            "msg_type": msg_type,
                            "msg": msg_content,
                        }
                        
                    except Exception as e:
                        logger.error(f"Failed to parse message: {e}")
                        continue
                
                # 没有消息，短暂等待后继续
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error reading from stream: {e}")
                break
        
        return None


# 全局长轮询工作者实例
long_poll_worker = LongPollWorker()