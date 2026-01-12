---
文档标题：概念设计 - 架构与配置设计
文档描述：描述 TODO Write 工具的三层架构设计、职责划分、数据流向以及 Config 配置设计。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发开发文档之外的文件时,尽量使用相对于项目根目录的相对路径
---

**目录**:
- [架构设计](#架构设计)
- [Config 设计](#config-设计)

## 架构设计

### 三层架构

```
┌─────────────────────────────────────────┐
│         Tool Layer                      │
│  ┌─────────────────────────────────┐    │
│  │  TodoWriteTool                  │    │
│  │  - __init__(config, backend)    │    │
│  │  - __call__(**kwargs)           │    │
│  │  - _create_todo()               │    │
│  │  - _update_todo()               │    │
│  │  - _delete_todo()               │    │
│  └─────────────────────────────────┘    │
└────────────────┬────────────────────────┘
                 │ 调用存储后端
                 │ create_todo()
                 │ get_todo()       (验证用)
                 │ update_todo()
                 │ delete_todo()
┌────────────────▼────────────────────────┐
│    Storage Backend Layer                │
│  ┌───────────────────────────────────┐  │
│  │  TodoStorageBackend (ABC)        │  │
│  │  - __init__(session_id)          │  │
│  │  - create_todo(todo_data)        │  │
│  │  - get_todo(todo_id)             │  │
│  │  - get_all_todos()               │  │
│  │  - update_todo(todo_id, updates) │  │
│  │  - delete_todo(todo_id)          │  │
│  └───────────────────────────────────┘  │
│                                          │
│  ┌──────────────┐  ┌─────────────────┐  │
│  │SessionStorage│  │   Memory        │  │
│  │  Backend     │  │   Backend       │  │
│  └──────────────┘  └─────────────────┘  │
└────────────────┬────────────────────────┘
                 │ 读写数据
┌────────────────▼────────────────────────┐
│       Storage Layer                      │
│  ┌───────────────────────────────────┐  │
│  │  u2a_session_storage (PostgreSQL) │  │
│  │  - storage: JSONB                 │  │
│  │  - session_id: UUID               │  │
│  └───────────────┬───────────────────┘  │
│                  │                        │
│  ┌───────────────▼───────────────────┐  │
│  │  Memory (dict)                    │  │
│  │  - {session_id: {todos: [...]}}   │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

### 职责划分

#### Tool Layer (工具层)

**职责**：
1. ✅ 接收和验证 LLM 传递的参数
2. ✅ 根据 `action` 参数分发到不同的处理方法
3. ✅ 调用存储后端的方法
4. ✅ 构造符合 LLM 理解的返回值
5. ✅ 处理异常并转换为友好错误消息

**不负责**：
- ❌ session_id 管理（由存储后端负责）
- ❌ 数据持久化细节（由存储后端负责）
- ❌ 数据库连接管理（由存储层负责）

#### Storage Backend Layer (存储后端层)

**职责**：
1. ✅ 持有 session_id（在 `__init__` 时注入）
2. ✅ 实现 CRUD 操作（create, get, update, delete）
3. ✅ 数据格式转换（业务对象 ↔ 存储格式）
4. ✅ 与存储层交互（数据库或内存）

**不负责**：
- ❌ 参数验证（由工具层负责）
- ❌ 返回值格式化（由工具层负责）
- ❌ 业务逻辑编排（由工具层负责）

### 数据流向

#### 创建 TODO 流程

```
LLM 调用
  ↓
TodoWriteTool.__call__(action="create", title="...", ...)
  ↓
TodoWriteParamValidate.model_validate()  [参数验证]
  ↓
_create_todo(param)
  ↓
storage_backend.create_todo(todo_data={...})
  ↓
SessionStorageTodoBackend:
  1. get_session_storage_by_session_id(self.session_id)
  2. 读取 storage["todos"]
  3. 追加新 todo
  4. update_session_storage_by_session_id(...)
  ↓
返回 ToolTaskResult(str_content="Todo created: {id}", json_content={...})
  ↓
LLM 收到结果
```

#### 更新 TODO 流程

```
LLM 调用
  ↓
TodoWriteTool.__call__(action="update", todo_id="...", updates={...})
  ↓
TodoWriteParamValidate.model_validate()  [参数验证]
  ↓
_update_todo(param)
  ↓
# 先验证 TODO 是否存在
storage_backend.get_todo(todo_id=...)
  ↓
# TODO 存在，执行更新
storage_backend.update_todo(todo_id=..., updates={...})
  ↓
返回 ToolTaskResult(str_content="Todo updated", json_content={...})
  ↓
LLM 收到结果
```

#### 删除 TODO 流程

```
LLM 调用
  ↓
TodoWriteTool.__call__(action="delete", todo_id="...")
  ↓
TodoWriteParamValidate.model_validate()  [参数验证]
  ↓
_delete_todo(param)
  ↓
# 先验证 TODO 是否存在
storage_backend.get_todo(todo_id=...)
  ↓
# TODO 存在，执行删除
storage_backend.delete_todo(todo_id=...)
  ↓
返回 ToolTaskResult(str_content="Todo deleted", json_content={...})
  ↓
LLM 收到结果
```

## Config 设计

### TodoWriteConfig 类定义

```python
from typing import Literal
from pydantic import BaseModel, Field

class TodoWriteConfig(SessionToolConfigBase):
    """Todo Write 工具的配置类"""

    # 是否启用工具（继承自基类）
    enabled: bool = True

    # 存储后端类型
    storage_backend: Literal["session_storage", "memory", "kwargs_DI"] = Field(
        default="session_storage",
        description="存储后端类型选择"
    )

    # 状态流转验证
    enforce_status_transitions: bool = Field(
        default=True,
        description="是否强制验证状态流转规则"
    )
```

### Config 字段说明

#### `enabled` 字段

- **类型**：`bool`
- **默认值**：`True`
- **说明**：控制工具是否启用。当 `False` 时，LLM 无法调用此工具
- **继承自**：`SessionToolConfigBase`

#### `storage_backend` 字段

- **类型**：`Literal["session_storage", "memory", "kwargs_DI"]`
- **默认值**：`"session_storage"`
- **说明**：控制使用哪种存储后端

##### storage_backend 的三种模式

| 模式值 | 含义 | 使用场景 | 后端实例创建方式 |
|--------|------|----------|------------------|
| `"session_storage"` | 使用 Session Storage | 生产环境默认模式 | `SessionStorageTodoBackend(session_id)` |
| `"memory"` | 使用内存存储 | 测试、临时场景 | `MemoryTodoBackend(session_id)` |
| `"kwargs_DI"` | 依赖注入 | 单元测试、自定义后端 | 从 `kwargs["storage_backend"]` 获取 |

#### `enforce_status_transitions` 字段

- **类型**：`bool`
- **默认值**：`True`
- **说明**：是否强制验证状态流转规则
- **行为**：
  - `True`：不允许 `pending → completed` 直接流转（必须经过 `in_progress`）
  - `False`：允许任意状态流转

### 默认配置

```python
DEFAULT_TOOL_CONFIG = {
    "todo_write": TodoWriteConfig(
        enabled=True,
        storage_backend="session_storage",
        enforce_status_transitions=True
    )
}
```

### 配置验证

虽然 Pydantic 会自动验证 `storage_backend` 字段的值，但可以添加自定义验证逻辑：

```python
from pydantic import field_validator

class TodoWriteConfig(SessionToolConfigBase):
    enabled: bool = True
    storage_backend: Literal["session_storage", "memory", "kwargs_DI"] = "session_storage"
    enforce_status_transitions: bool = True

    @field_validator("storage_backend")
    @classmethod
    def validate_storage_backend(cls, v):
        """验证 storage_backend 值（Pydantic 会自动验证 Literal，这里可留作扩展）"""
        return v
```

---

**下一步**：请参考 [`03_protocol_and_implementation.md`](./03_protocol_and_implementation.md) 了解协议类设计、存储后端实现和执行逻辑设计。
