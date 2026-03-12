from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

class CommandRequest(BaseModel):
    command_name: str = Field(description="命令名称")
    session_id: str = Field(description="会话ID，用于隔离不同会话的命令执行")
    params: Dict[str, Any] = Field(default_factory=dict, description="命令参数")

class CommandResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error_message: Optional[str] = None
    command_name: Optional[str] = None
    rollback_performed: bool = False  # 标记是否执行了回滚