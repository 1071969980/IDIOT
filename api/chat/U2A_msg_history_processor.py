import json
import uuid
from datetime import datetime, UTC
from typing import Literal, Union
from pydantic import BaseModel
from .base_processor import BaseProcessor
from api.redis.constants import CLIENT as redis_client

U2AMessageHistoryType = Literal[
    "user_text_msg",
    "agent_text_msg",
    "tool_call",
    "tool_response",
]

class _UserTextMsgData(BaseModel):
    content: str

class _AgentTextMsgData(BaseModel):
    # check "status" def in "api/chat/sql_stat/u2a_msg/U2AMsg.sql"
    status: Literal['streaming', 'stop', 'complete', 'error'] 
    content: str | None

class _ToolCallData(BaseModel):
    tool_name: str
    tool_args: dict | None

class _ToolResponseData(BaseModel):
    tool_name: str
    tool_output: str | None

class U2AMessageHistory(BaseModel):
    ss_uuid: str
    msg_uuid: str
    type: U2AMessageHistoryType
    content: Union[_UserTextMsgData,  # noqa: UP007
                   _AgentTextMsgData,
                   _ToolCallData,
                   _ToolResponseData,
                   None]
    
class U2AMessageHistoryProcessor(BaseProcessor[U2AMessageHistory]):
    pass