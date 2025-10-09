"""
HTTP Worker API路由器
HTTP长轮询服务路由定义
"""

import asyncio
import time
from fastapi import APIRouter, HTTPException, Depends
from loguru import logger

from api.authentication.constant import AUTH_HEADER
from api.human_in_loop.http_worker.long_poll_worker import long_poll_worker
from api.authentication.utils import get_current_active_user
from api.authentication.sql_stat.utils import _User
from api.human_in_loop.http_worker.data_model import (
    HTTPPollRequest, HTTPJsonRPCRequest, HTTPJsonRPCResponse, HTTPJsonRPCError, generate_request_id
)

# 创建API路由器
router = APIRouter(
    prefix="/hil/http",
    tags=["human-in-loop-http"]
)


@router.post("/{stream_identifier}/poll", response_model=HTTPJsonRPCRequest)
async def poll_messages(
    stream_identifier: str,
    request: HTTPPollRequest,
    auth_header: str = Depends(AUTH_HEADER), 
    user: _User = Depends(get_current_active_user)
) -> HTTPJsonRPCRequest:
    """轮询消息端点"""
    
    start_time = time.time()
    
    try:
        # 直接返回JsonRPC请求格式
        response = await long_poll_worker.poll_messages(request, stream_identifier, user.user_name)
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


@router.post("/{stream_identifier}/ack", status_code=204)
async def ack_message(
    stream_identifier: str,
    request: HTTPJsonRPCResponse,
    auth_header: str = Depends(AUTH_HEADER),
    user: _User = Depends(get_current_active_user)
):
    """确认消息接收端点
    
    Example payload:
    {
        "jsonrpc": "2.0",
        "id": "string",
        "result": {
            "HIL_msg_id": "7c21ea75-0035-48e0-9944-41a8e0077c2f",
            "msg": "ack"
        }
    }
    """
    try:
        # 从 JsonRPCResponse 中提取 HIL_msg_id
        if not request.result or not request.result.get("HIL_msg_id"):
            raise HTTPException(status_code=400, detail="Missing HIL_msg_id in result")
        
        HIL_msg_id = request.result.get("HIL_msg_id")
        success = await long_poll_worker.ack_message(HIL_msg_id, stream_identifier, user.user_name)
        if not success:
            raise HTTPException(status_code=404, detail="Message not found")
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error in ack_message: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{stream_identifier}/respond", response_model=HTTPJsonRPCResponse)
async def send_response(
    stream_identifier: str,
    request: HTTPJsonRPCRequest,
    auth_header: str = Depends(AUTH_HEADER),
    user: _User = Depends(get_current_active_user)
) -> HTTPJsonRPCResponse:
    """发送响应端点"""
    
    start_time = time.time()
    
    try:
        # 验证请求方法
        if request.method != "HIL_interrupt_response":
            return HTTPJsonRPCResponse(
                id=request.id,
                error={
                    "code": -32601,
                    "message": "Method not found",
                    "data": {"expected_method": "HIL_interrupt_response"}
                }
            )
        
        # 验证参数
        if not request.params or not request.params.get("HIL_msg_id"):
            return HTTPJsonRPCResponse(
                id=request.id,
                error={
                    "code": -32602,
                    "message": "Invalid params",
                    "data": {"required_params": ["HIL_msg_id"], "alternative_params": ["msg"]}
                }
            )
        
        # 提取参数
        HIL_msg_id = request.params.get("HIL_msg_id")
        msg = request.params.get("msg")
        
        # 调用底层服务
        success = await long_poll_worker.ack_message(HIL_msg_id, stream_identifier, user.user_name)
        if not success:
            raise HTTPException(status_code=404, detail="Message not found")
        await long_poll_worker.send_response_with_params(HIL_msg_id, msg, stream_identifier, user.user_name)
        
        return HTTPJsonRPCResponse(
            id=request.id,
            result="ack"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in send_response: {e}")
        return HTTPJsonRPCResponse(
            id=request.id,
            error={
                "code": -32603,
                "message": "Internal server error",
                "data": {"exception": str(e)}
            }
        )



@router.get("/")
async def root():
    """根端点"""
    return {
        "service": "Human In Loop HTTP Worker",
        "version": "1.0.0",
        "endpoints": [
            "POST /hil/http/{stream_identifier}/poll",
            "POST /hil/http/{stream_identifier}/respond",
            "POST /hil/http/{stream_identifier}/ack",
        ]
    }