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
            - "storage_snapshot": 使用 u2a_session_task 的 storage_snapshot 字段（默认）
            - "session_storage": 使用 u2a_session_storage
            - "memory": 使用内存存储
            - "local": 使用本地文件系统存储
            - "kwargs_DI": 从 kwargs 依赖注入存储后端实例
        local_base_path: 本地文件系统基础路径（仅 storage_backend='local' 时使用）
        enforce_status_transitions: 是否强制验证状态流转规则
    """

    enabled: bool = True
    explicit: bool = True
    storage_backend: Literal["storage_snapshot", "session_storage", "memory", "local", "kwargs_DI"] = Field(
        default="storage_snapshot",
        description=(
            "存储后端类型选择。"
            "'storage_snapshot' 使用 u2a_session_task 的 storage_snapshot 字段，按任务节点隔离（默认）；"
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

    支持三种操作模式，每个操作都支持单个和批量：
    - create: 创建新的 Todo
    - update: 更新现有 Todo
    - delete: 删除 Todo
    """

    # Action 参数
    action: Literal["create", "update", "delete"] = Field(
        description="要执行的操作类型：'create'（创建）、'update'（更新）或 'delete'（删除）"
    )

    # Title 参数（支持单个或批量）
    title: str | list[str] | None = Field(
        default=None,
        description=(
            "Todo 的标题（唯一标识符）。"
            "可以是单个标题字符串或标题列表。"
            "create/update/delete 操作都需要。"
        )
    )

    status: Literal["pending", "completed"] | None = Field(
        default=None,
        description=(
            "Todo 的状态。可选值："
            "'pending'（待办）、、"
            "'completed'（已完成）、"
            "update 操作时应用到所有指定的 todo。"
        )
    )

    priority: int | None = Field(
        default=None,
        description=(
            "Todo 的优先级，数值越大优先级越高。"
            "update 操作时应用到所有指定的 todo。"
        )
    )

    model_config = ConfigDict(extra="allow")  # 允许额外字段（向前兼容）


# 默认工具配置
DEFAULT_TOOL_CONFIG = {
    TOOL_NAME: TodoWriteConfig(
        enabled=True,
        explicit=True,
        storage_backend="storage_snapshot"
    )
}


# 工具生成参数（用于 LLM Function Calling）
TODO_WRITE_GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name=TOOL_NAME,
        description="""
使用此工具为当前会话创建和管理结构化的任务列表。这有助于跟踪进度、组织复杂任务，并向用户展示你的工作细致周全。

此工具还能帮助用户了解任务进度以及请求的整体进展。

**何时使用此工具**

在以下情况下主动使用此工具：

1. 复杂的多步骤任务 - 需要仔细规划和多个操作的任务

2. 平行的任务 - 当任务多个彼此平行的复杂操作时

3. 用户明确请求待办事项列表 - 当用户直接要求您使用待办事项列表时

4. 用户提供多个任务 - 当用户提供待办事项列表（编号或逗号分隔）时

5. 收到新指令后 - 立即将用户需求记录为待办事项

6. 完成任务后，将其标记为已完成，并添加在实施过程中发现的任何新的后续任务。

**何时不应使用此工具**

以下情况请勿使用此工具：

1. 只有一个简单的任务

2. 任务微不足道，跟踪它对组织管理没有任何好处

3. 任务可以在少于 3 个简单的步骤内完成

4. 任务纯粹是对话或信息传递

注意：如果只有一个简单的任务，则不应使用此工具。在这种情况下，最好直接执行该任务。

注意：此工具的写入结果会以系统消息的身份，在<todo_list>的标签中提供
        """,
        parameters=turn_pydantic_model_to_json_schema(TodoWriteParamDefine),
        parameters_example={
            "action": "create",
            "title": "完成代码审查",
            "status": "pending",
            "priority": 5
        } # extra fields for tool param example, some llm chat template rendering it.
    ) # type: ignore
)
