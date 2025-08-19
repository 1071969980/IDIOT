"""
this file def data model by JSON RPC 2.0 protocol 
"""

from pydantic import BaseModel, field_validator, model_validator
from typing import Literal

RPC_AVAILABLE_METHODS = Literal[
    "init_session",
    "HIL_interrupt_request",
    "HIL_interrupt_response",
    "Notification",
]

ERROR_CODES = [
    -32700, # Parse error.
    -32600, # Invalid request.
    -32601, # Method not found.
    -32602, # Invalid params.
    -32603, # Internal error.
]

AUTH_TOKEN_KEY = "auth_token"

class JsonRPCRequest(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | None
    method: RPC_AVAILABLE_METHODS
    params: dict | None

    # 要求pydantic检查params中必须有auth_token字段
    @field_validator('params')
    @classmethod
    def validate_params(cls, v):
        if v is not None and not isinstance(v, dict):
            raise ValueError('params must be a dict')
        if v is not None and AUTH_TOKEN_KEY not in v:
            msg = f"params must contain {AUTH_TOKEN_KEY} field"
            raise ValueError(msg)
        return v
    
class JsonRPCError(BaseModel):
    code: int
    message: str
    data: dict | None

    @field_validator('code')
    @classmethod
    def validate_code(cls, v):
        if v not in ERROR_CODES:
            raise ValueError('code must be one of %s' % ERROR_CODES)
        return v

class JsonRPCResponse(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | None
    result: dict | str | None
    error: dict | None

    @model_validator(mode="after")
    def validate_result_and_error(self):
        if self.result is not None and self.error is not None:
            raise ValueError('result and error cannot be both set')
        return self