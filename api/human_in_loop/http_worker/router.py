"""
HTTP Worker API路由器
HTTP长轮询服务路由定义
"""

import asyncio
import time
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from loguru import logger

from api.human_in_loop.http_worker.long_poll_worker import long_poll_worker
from api.authentication.utils import get_current_active_user
from api.authentication.sql_stat.utils import _User
from api.human_in_loop.http_worker.data_model import (
    HILPollRequest,
    HILPollResponse,
    HILResponseRequest
)

# 创建API路由器
router = APIRouter(
    prefix="/hil",
    tags=["human-in-loop-http"]
)


@router.post("/poll", response_model=HILPollResponse)
async def poll_messages(
    request: HILPollRequest,
    user: _User = Depends(get_current_active_user)
) -> HILPollResponse:
    """轮询消息端点"""
    
    start_time = time.time()
    
    try:
        # 直接返回JsonRPC请求格式
        response = await long_poll_worker.poll_messages(str(request.session_task_id), request.redis_last_id, request.timeout)
        if response is None:
            # 无消息时返回204状态码
            raise HTTPException(status_code=204, detail="No messages available")
        return response
    except HTTPException as e:
        # 直接抛出HTTP异常
        raise e
    except Exception as e:
        logger.error(f"Error in poll_messages: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# @router.post("/ack")
# async def ack_message(
#     request: HILResponseRequest,
#     user: _User = Depends(get_current_active_user)
# ):
#     """确认消息接收端点
    
#     Example payload:
#     {
#         "jsonrpc": "2.0",
#         "id": "string",
#         "result": {
#             "HIL_msg_id": "7c21ea75-0035-48e0-9944-41a8e0077c2f",
#             "msg": "ack"
#         }
#     }
#     """
#     try:
#         # 从 JsonRPCResponse 中提取 HIL_msg_id
#         HIL_msg_id = request.hil_msg_id
#         success = await long_poll_worker.ack_message(HIL_msg_id, request.stream_identifier, user.user_name)
#         if not success:
#             raise HTTPException(status_code=404, detail="Message not found")
#     except HTTPException as e:
#         raise e
#     except Exception as e:
#         logger.error(f"Error in ack_message: {e}")
#         raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/respond")
async def send_response(
    request: HILResponseRequest,
    user: _User = Depends(get_current_active_user)
):
    """发送响应端点"""
    
    start_time = time.time()
    
    try:
        # 提取参数
        HIL_msg_id = request.hil_msg_id
        msg = request.msg
        
        # 调用底层服务
        success = await long_poll_worker.ack_message(HIL_msg_id, str(request.session_task_id), user.user_name)
        if not success:
            raise HTTPException(status_code=404, detail="Message not found")
        await long_poll_worker.send_response_with_params(HIL_msg_id, msg, str(request.session_task_id), user.user_name)
        # TODO: try serialize HIL result into postgresql
        return 
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")