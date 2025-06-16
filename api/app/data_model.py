from pydantic import BaseModel
from typing import Any

class ErrorResponse(BaseModel):
    """
    错误响应模型
    """
    status_code: int
    detail: Any  # 错误信息