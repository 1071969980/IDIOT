from pydantic import BaseModel
from typing import Any
from enum import Enum

class TaskStatus(str, Enum):
    """
    任务状态枚举
    """
    init = "init"
    running = "running"
    success = "success"
    failed = "failed"

class ErrorResponse(BaseModel):
    """
    错误响应模型
    """
    status_code: int
    detail: Any  # 错误信息