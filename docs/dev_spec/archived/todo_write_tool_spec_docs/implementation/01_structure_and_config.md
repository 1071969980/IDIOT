---
文档标题：实现细节 - 目录结构与配置
文档描述：描述 TODO Write 工具的目录结构设计、Config 和参数定义的完整实现。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [目录结构设计](#目录结构设计)
- [Config 和参数定义实现](#config-和参数定义实现)

## 目录结构设计

### 完整目录结构

```
api/agent/tools/todo/
├── __init__.py
├── storage_backend/                    # 存储后端模块
│   ├── __init__.py
│   ├── base.py                         # TodoStorageBackend ABC
│   ├── session_storage.py              # SessionStorageTodoBackend
│   └── memory.py                       # MemoryTodoBackend
├── config_data_model.py                # 配置和参数定义
└── constructor.py                      # 工具实现和构造器
```

### 文件职责说明

| 文件 | 职责 | 依赖 |
|------|------|------|
| `storage_backend/base.py` | 定义抽象基类 | `abc`, `uuid.UUID`, `typing` |
| `storage_backend/session_storage.py` | Session Storage 实现 | `base.py`, `u2a_session_storage.utils` |
| `storage_backend/memory.py` | 内存存储实现 | `base.py`, `asyncio` |
| `config_data_model.py` | 配置和参数类 | `SessionToolConfigBase`, `Pydantic` |
| `constructor.py` | 工具类和构造函数 | 所有上述模块 |

## Config 和参数定义实现

### config_data_model.py 完整实现

**文件位置**：`api/agent/tools/todo/config_data_model.py`

```python
"""
TODO Write 工具的配置和参数定义
"""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

# 引入项目的基础配置类
from api.agent.tools.config_data_model import SessionToolConfigBase

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
            - "kwargs_DI": 从 kwargs 依赖注入存储后端实例
        enforce_status_transitions: 是否强制验证状态流转规则
    """

    enabled: bool = True

    storage_backend: Literal["session_storage", "memory", "kwargs_DI"] = Field(
        default="session_storage",
        description=(
            "存储后端类型选择。"
            "'session_storage' 使用 PostgreSQL 的 session_storage 表；"
            "'memory' 使用内存存储；"
            "'kwargs_DI' 从依赖注入获取存储后端实例。"
        )
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

    description: str | None = Field(
        default=None,
        description="Todo 的详细描述（所有操作可选）"
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

    tags: list[str] | None = Field(
        default=None,
        description="Todo 的标签列表，用于组织和分类"
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
            "description": "审查 PR #123 的代码变更",
            "status": "pending",
            "priority": 5,
            "tags": ["review", "urgent"]
        } # extra fields for tool param example, some llm chat template rendering it.
    ) # type: ignore
)
```

### 关键实现要点

1. **类型注解使用**：使用 `str | None` 而非 `Optional[str]`（Python 3.10+ 风格）
2. **字段描述**：每个字段都有详细的 `description`，帮助 LLM 理解参数用途
3. **默认值处理**：所有可选字段默认为 `None`
4. **额外字段支持**：`extra = "allow"` 允许未来扩展

### Config 和参数的关系

```
TodoWriteConfig (控制工具行为)
  ├─ enabled: bool
  ├─ storage_backend: Literal["session_storage", "memory", "kwargs_DI"]
  └─ enforce_status_transitions: bool

TodoWriteParamDefine (LLM 调用时传递的参数)
  ├─ action: Literal["create", "update", "delete"]
  ├─ title: str | None
  ├─ description: str | None
  ├─ status: Literal[...] | None
  ├─ priority: int | None
  ├─ tags: list[str] | None
  └─ todo_id: str | None
```

**区别**：
- `TodoWriteConfig`：在工具初始化时配置，控制工具的整体行为
- `TodoWriteParamDefine`：LLM 每次调用工具时传递的参数，控制单次操作

---

**下一步**：请参考 [`02_storage_backend.md`](./02_storage_backend.md) 了解存储后端协议类和具体实现的完整代码。
