from pydantic import BaseModel
from typing import Dict, Any, Optional

class CommandRequest(BaseModel):
    command_name: str
    params: Dict[str, Any]

class CommandResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error_message: Optional[str] = None
    command_name: Optional[str] = None
    rollback_performed: bool = False  # 标记是否执行了回滚