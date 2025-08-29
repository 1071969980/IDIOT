"""
HTTP Worker数据模型
基于JSON-RPC 2.0协议的HTTP长轮询版本
"""

from pydantic import BaseModel, field_validator, model_validator
from typing import Literal, Optional, Dict, Any
import uuid

# 对齐WebSocket worker的常量定义
RPC_AVAILABLE_METHODS = Literal[
    "HIL_interrupt_request",
    "HIL_interrupt_response",
    "Notification",
]

ERROR_CODES = [
    -32700,  # Parse error
    -32600,  # Invalid request
    -32601,  # Method not found
    -32602,  # Invalid params
    -32603,  # Internal error
]

AUTH_TOKEN_KEY = "auth_token"


class HTTPPollRequest(BaseModel):
    """轮询请求模型"""
    timeout: int = 30


class HTTPJsonRPCRequest(BaseModel):
    """HTTP JSON-RPC请求模型 - 对齐WebSocket worker"""
    jsonrpc: Literal["2.0"] = "2.0"
    id: Optional[str] = None
    method: RPC_AVAILABLE_METHODS
    params: Optional[Dict[str, Any]] = None
    

class HTTPJsonRPCResponse(BaseModel):
    """HTTP JSON-RPC响应模型 - 对齐WebSocket worker"""
    jsonrpc: Literal["2.0"] = "2.0"
    id: Optional[str] = None
    result: Optional[Dict[str, Any] | str] = None
    error: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def validate_result_and_error(self):
        if self.result is not None and self.error is not None:
            raise ValueError('result and error cannot be both set')
        return self


class HTTPJsonRPCError(BaseModel):
    """HTTP JSON-RPC错误模型 - 对齐WebSocket worker"""
    code: int
    message: str
    data: Optional[Dict[str, Any]] = None

    @field_validator('code')
    @classmethod
    def validate_code(cls, v):
        if v not in ERROR_CODES:
            raise ValueError('code must be one of %s' % ERROR_CODES)
        return v


class HTTPAckRequest(BaseModel):
    """确认消息请求模型"""
    msg_id: str


def generate_request_id() -> str:
    """生成唯一的请求ID"""
    return str(uuid.uuid4())