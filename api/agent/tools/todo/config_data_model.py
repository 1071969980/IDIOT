"""
TODO Write 工具的配置和参数定义
"""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

# 引入项目的基础配置类
from api.agent.tools.config_data_model import (
    SessionToolConfigBase,
    turn_pydantic_model_to_json_schema
)
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition

# 工具名称
TOOL_NAME = "todo_write"


class TodoWriteConfig(SessionToolConfigBase):
    """
    Todo Write 工具的配置类

    Attributes:
        enabled: 是否启用工具
        storage_backend: 存储后端类型选择
            - "session_storage": 使用 u2a_session_storage (默认)
            - "memory": 使用内存存储
            - "local": 使用本地文件系统存储
            - "kwargs_DI": 从 kwargs 依赖注入存储后端实例
        local_base_path: 本地文件系统基础路径（仅 storage_backend='local' 时使用）
        enforce_status_transitions: 是否强制验证状态流转规则
    """

    enabled: bool = True

    storage_backend: Literal["session_storage", "memory", "local", "kwargs_DI"] = Field(
        default="session_storage",
        description=(
            "存储后端类型选择。"
            "'session_storage' 使用 PostgreSQL 的 session_storage 表；"
            "'memory' 使用内存存储；"
            "'local' 使用本地文件系统；"
            "'kwargs_DI' 从依赖注入获取存储后端实例。"
        )
    )

    local_base_path: str | None = Field(
        default=None,
        description="本地文件系统的基础路径（仅 storage_backend='local' 时使用）"
    )

    enforce_status_transitions: bool = Field(
        default=True,
        description=(
            "是否强制验证状态流转规则。"
            "如果为 True，则不允许 pending→completed 直接流转（必须经过 in_progress）。"
            "如果为 False，则允许任意状态流转。"
        )
    )


class TodoWriteParamDefine(BaseModel):
    """
    Todo Write 工具的参数定义

    支持三种操作模式：
    - create: 创建新的 Todo
    - update: 更新现有 Todo
    - delete: 删除 Todo
    """

    # Action 参数
    action: Literal["create", "update", "delete"] = Field(
        description="要执行的操作类型：'create'（创建）、'update'（更新）或 'delete'（删除）"
    )

    # Create 操作参数
    title: str | None = Field(
        default=None,
        description="Todo 的标题（create 操作必需）"
    )

    status: Literal["pending", "in_progress", "completed", "cancelled"] | None = Field(
        default=None,
        description=(
            "Todo 的状态。可选值："
            "'pending'（待办）、'in_progress'（进行中）、"
            "'completed'（已完成）、'cancelled'（已取消）"
        )
    )

    priority: int | None = Field(
        default=None,
        description="Todo 的优先级，数值越大优先级越高，默认为 0"
    )

    # Update/Delete 操作参数
    todo_id: str | None = Field(
        default=None,
        description="要更新或删除的 Todo ID（update 和 delete 操作必需）"
    )

    model_config = ConfigDict(extra="allow")  # 允许额外字段（向前兼容）


# 默认工具配置
DEFAULT_TOOL_CONFIG = {
    TOOL_NAME: TodoWriteConfig(
        enabled=True,
        storage_backend="session_storage"
    )
}


# 工具生成参数（用于 LLM Function Calling）
TODO_WRITE_GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name=TOOL_NAME,
        description="管理当前对话中的 TODO 项目。你可以创建、更新或删除 TODO 来跟踪任务和进度。",
        parameters=turn_pydantic_model_to_json_schema(TodoWriteParamDefine),
        parameters_example={
            "action": "create",
            "title": "完成代码审查",
            "status": "pending",
            "priority": 5
        } # extra fields for tool param example, some llm chat template rendering it.
    ) # type: ignore
)
