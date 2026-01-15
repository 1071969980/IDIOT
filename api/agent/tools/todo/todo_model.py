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
    created_at: str = Field(description="创建时间 (ISO 8601 格式)")
    updated_at: str = Field(description="更新时间 (ISO 8601 格式)")

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )

    @field_validator('created_at', 'updated_at')
    @classmethod
    def validate_iso8601(cls, v: str) -> str:
        """验证 ISO 8601 格式"""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except ValueError:
            raise ValueError(f"'{v}' is not a valid ISO 8601 datetime")
        return v
