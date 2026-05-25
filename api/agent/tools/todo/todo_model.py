"""
Todo 数据模型

使用 Pydantic 规范化 Todo 数据结构，提供类型安全和数据验证。
"""

from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Literal


class TodoModel(BaseModel):
    """
    Todo 数据模型

    使用 title 作为唯一标识符，移除 UUID 字段。
    """

    title: str = Field(description="Todo 标题（唯一标识符）")
    status: Literal["pending", "completed"] = Field(
        default="pending",
        description="Todo 状态"
    )
    priority: int = Field(
        default=0,
        ge=0,
        description="优先级，数值越大优先级越高"
    )
    description: str | None = Field(
        default=None,
        max_length=500,
        description="Todo 的详细描述或备注"
    )

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )