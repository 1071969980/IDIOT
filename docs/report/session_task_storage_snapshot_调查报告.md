# session_task 的 storage_snapshot 机制调查报告

## 1. 概述

`storage_snapshot` 是 `u2a_session_tasks` 表中的一个 **JSONB 字段**，用于在任务节点树上存储和继承结构化数据。它是多个工具和功能的共享存储层，支持按任务节点隔离、沿树结构继承祖先快照。

**核心设计理念**：每个 task 节点拥有独立的 `storage_snapshot`，初始化时从最近祖先继承（深拷贝），后续修改互不影响。

---

## 2. 数据库层

### 2.1 表定义

文件：`api/chat/sql_stat/u2a_session_task/U2ASessionTask.sql`

```sql
CREATE TABLE IF NOT EXISTS u2a_session_tasks (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    session_id UUID NOT NULL,
    user_id UUID NOT NULL,
    status VARCHAR(32) NOT NULL CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')),
    parent_task_id UUID,
    branch_id UUID,
    seq_in_session INT NOT NULL DEFAULT 0,
    tree_path ltree NOT NULL,          -- ltree 路径，用于祖先查询
    context_breakpoints INT[] DEFAULT '{}',
    storage_snapshot JSONB DEFAULT NULL, -- 本报告的核心字段
    logic_mark JSONB DEFAULT NULL,
    ...
);
```

- 使用 GIN 索引加速 JSONB 查询：`idx_u2a_session_tasks_storage_snapshot`
- 使用 ltree + GIST 索引支持祖先路径查询：`idx_u2a_session_tasks_tree_path`

### 2.2 与 storage_snapshot 相关的 SQL 操作

| SQL 名称 | 用途 |
|----------|------|
| `UpdateSessionTaskStorageSnapshot` | 直接更新指定 task 的 `storage_snapshot` |
| `QueryNearestAncestorStorageSnapshot` | 沿 tree_path 向上查找最近的 `storage_snapshot` 非空的祖先 |
| `CopyStorageSnapshotFromNearestAncestor` | 从最近祖先复制 `storage_snapshot` 到当前 task |

### 2.3 继承查询逻辑 (`QueryNearestAncestorStorageSnapshot`)

采用**两阶段优先级**策略：
1. **先查直接父节点** (`parent_task_id`)，若父节点有 `storage_snapshot` 则直接使用
2. 若父节点没有，再沿 `tree_path` 向上搜索所有祖先，取 `seq_in_session` 最大的（离 leaf 最近）

### 2.4 Python 数据模型

文件：`api/chat/sql_stat/u2a_session_task/utils.py`

```python
@dataclass
class _U2ASessionTask:
    ...
    storage_snapshot: dict[str, Any] | None
    ...
```

关键函数：

| 函数 | 用途 |
|------|------|
| `update_task_storage_snapshot(task_id, storage_snapshot)` | 更新指定 task 的 `storage_snapshot` |
| `get_nearest_ancestor_storage_snapshot(task_id)` | 查询最近祖先的 `storage_snapshot` |
| `copy_storage_snapshot_from_nearest_ancestor(task_id)` | 从最近祖先复制到自身 |

---

## 3. 初始化与继承

文件：`api/chat/sql_stat/u2a_session_branch_task/operations.py`

### 3.1 创建时机

新 task 在以下三种场景中被创建，每种都处理 `storage_snapshot` 的初始化：

#### 3.1.1 `create_root_task_with_branch` — 创建会话的第一个 task

- `storage_snapshot` 初始为 `None`
- 随后立即设为空 dict `{}`（root 无祖先）

```python
# 4.1 root task 无祖先，直接设 storage_snapshot 为空 dict
await conn.execute(
    text(UPDATE_SESSION_TASK_STORAGE_SNAPSHOT).bindparams(...),
    {"id_value": new_task_id, "storage_snapshot_value": {}},
)
```

#### 3.1.2 `append_task_to_branch` — 在现有分支末尾追加新 task

- 先 INSERT task（`storage_snapshot = None`）
- 再执行 `CopyStorageSnapshotFromNearestAncestor`
- 如果没有祖先有 `storage_snapshot`，则设为空 dict `{}`

#### 3.1.3 `fork_branch` — 从历史 task 分叉出新分支

- 同 `append_task_to_branch` 的继承逻辑

#### 3.1.4 `get_or_create_pending_task` — 获取或创建 pending task

- 同样的继承模式：INSERT → 复制祖先 → 兜底空 dict

### 3.2 继承模式总结

所有新 task 的 `storage_snapshot` 初始化遵循统一流程：

```
INSERT task (storage_snapshot=NULL)
  → CopyStorageSnapshotFromNearestAncestor
    → 成功：继承最近祖先的完整快照
    → 失败（无祖先有快照）：设为空 dict {}
```

---

## 4. storage_snapshot 中存储的数据（使用者）

`storage_snapshot` 是一个共享 JSONB 容器，不同工具/功能在其中各占一个 key。

### 4.1 Key: `"todos"` — Todo 工具

文件：`api/agent/tools/todo/storage_backend/storage_snapshot.py`

- **工具**：`todo_write`
- **存储结构**：
  ```json
  {
    "todos": [
      {"title": "...", "status": "pending", "priority": 0, "description": "...", ...}
    ]
  }
  ```
- **后端类**：`StorageSnapshotTodoBackend`
- **操作模式**：全量读写，所有写操作在 Redis 分布式锁保护下执行
- **锁**：`LockNames.task_storage_snapshot(task_id)`

#### 操作方法

| 方法 | 说明 |
|------|------|
| `_initialize()` | 检查 task 存在性，初始化 `todos` key |
| `create_todo(todo)` | 在 `todos` 数组中追加（锁保护） |
| `get_todo(title)` / `get_all_todos()` | 读取（无锁） |
| `update_todo(title, updates)` | 按 title 查找并更新（锁保护） |
| `delete_todo(title)` | 按 title 删除（锁保护） |
| `save_all_todos(todos)` | 原子替换全部列表（锁保护） |

### 4.2 Key: `"loaded_skills"` — Skill 加载工具

文件：`api/agent/tools/skills/load_skill/constructor.py`

- **工具**：`load_skill`
- **存储结构**：
  ```json
  {
    "loaded_skills": ["skill_name_1", "skill_name_2"]
  }
  ```
- **操作**：追加技能名称到列表，防止重复加载
- **锁**：`LockNames.task_storage_snapshot(session_task_id)`

### 4.3 Key: `"session_config_overlay"` — 会话配置覆盖层

文件：`api/agent/session_agent_config/crud.py`

- **使用者**：多个 session_agent_config 命令
- **存储结构**：
  ```json
  {
    "session_config_overlay": {
      "tools_config": {
        "bash": {"enabled": true, "explicit": false}
      },
      "mcp_config": {
        "servers": [...]
      }
    }
  }
  ```
- **设计模式**：基础配置（`u2a_session_agent_config` 表）+ overlay（`storage_snapshot`）深度合并
- **常量定义**：`SESSION_CONFIG_OVERLAY_KEY_IN_TASK_STORAGE_SNAPSHOT = "session_config_overlay"`（在 `api/agent/session_agent_config/constants.py`）

#### 使用该 overlay 的命令

| 命令 | 文件 | 修改内容 |
|------|------|----------|
| `UpdateToolsStatusCommand` | `api/app/chat/session_agent_config/command/update_tools_status/command.py` | 覆盖工具的 enabled/explicit |
| `UpdateMcpServersConfigCommand` | `api/app/chat/session_agent_config/command/update_mcp_servers_config/command.py` | 覆盖 MCP 服务器配置 |

#### 配置合并流程

在 `process_pending_messages`（`api/app/chat/process_pending_messages.py`）中生效：

```python
# 获取基础配置
session_config = SessionAgentConfig.model_validate(session_config_row.config)
# 从 storage_snapshot 读取 overlay
if SESSION_CONFIG_OVERLAY_KEY_IN_TASK_STORAGE_SNAPSHOT in task_storage_snapshot:
    session_config_overlay = task_storage_snapshot.get(...)
    session_config_final = deep_update_dict(session_config_base, session_config_overlay)
    session_config = SessionAgentConfig.model_validate(session_config_final)
```

也提供统一工具函数 `get_effective_session_config()`（在 `crud.py` 中）。

---

## 5. 并发控制

### 5.1 分布式锁

所有对 `storage_snapshot` 的写操作都通过 Redis 分布式锁保护，锁名格式：

```
task_storage_snapshot:{task_id}
```

定义在 `api/redis/lock_names.py` 的 `LockNames.task_storage_snapshot(task_id)`。

### 5.2 锁使用模式

统一的 Read-Judge-Write 模式：

```python
lock_key = LockNames.task_storage_snapshot(task_id)
async with RedisDistributedLock(lock_key):
    task = await get_task(task_id)
    snapshot = task.storage_snapshot
    # ... 修改 snapshot ...
    await update_task_storage_snapshot(task_id, snapshot)
```

### 5.3 锁使用者清单

| 使用者 | 操作 |
|--------|------|
| `StorageSnapshotTodoBackend.create_todo()` | 写 todos |
| `StorageSnapshotTodoBackend.update_todo()` | 写 todos |
| `StorageSnapshotTodoBackend.delete_todo()` | 写 todos |
| `StorageSnapshotTodoBackend.save_all_todos()` | 写 todos |
| `StorageSnapshotTodoBackend._initialize()` | 写 todos（初始化） |
| `LoadSkillTool.__call__()` | 写 loaded_skills |
| `UpdateToolsStatusCommand.execute()` | 写 session_config_overlay |
| `UpdateMcpServersConfigCommand.execute()` | 写 session_config_overlay |

---

## 6. 数据流全景

```
用户发消息 → get_or_create_pending_task()
                ↓
          INSERT task (storage_snapshot=NULL)
                ↓
          CopyStorageSnapshotFromNearestAncestor → 继承祖先快照
                ↓ (若无祖先)
          设 storage_snapshot = {}
                ↓
    ┌───────────┬───────────────┬──────────────────┐
    ↓           ↓               ↓                  ↓
  Todo工具   Skill工具    Config命令         process_pending
  "todos"   "loaded_     "session_config     读取 overlay
             skills"      _overlay"          合并生效配置
```

---

## 7. 一致性保障机制（已实施）

### 问题

当 agent 处理 task（status=processing）时，工具修改该 task 的 `storage_snapshot`。但并发的业务流程（send_message, config 命令）可能触发 `get_or_create_pending_task`，创建新 pending task 并从父节点复制此时可能已过时的 `storage_snapshot`。

### 措施 1：SQL 层面强制 — 仅 pending task 可修改

`UpdateSessionTaskStorageSnapshot` SQL 添加 `AND status = 'pending'` 守卫：

```sql
UPDATE u2a_session_tasks
SET storage_snapshot = :storage_snapshot_value
WHERE id = :id_value AND status = 'pending';
```

`update_task_storage_snapshot()` 在 task 非 pending 时自然返回 `False`（`rowcount == 0`）。

### 措施 2：工具动态解析最新 pending task

Todo 和 LoadSkill 工具不再使用固定的 `session_task_id`，而是存储 `session_id` + `branch_name` + `user_id`，在每次操作前通过 `get_or_create_pending_task()` 动态解析最新的 pending task_id。

**核心原则**：pending 状态可写，processing 之后逻辑只读。

---

## 8. 业务层的创建时机

从业务代码追踪，`storage_snapshot` 在以下场景中被创建或初始化：

### 7.1 会话创建时 — `POST /sessions/create`

文件：`api/app/chat/sessions.py` → `create_session()`

```
用户创建新会话 → insert_session → insert_session_config
             → create_root_task_with_branch(session_id, user_id, "main", "user")
```

- 调用底层 `create_root_task_with_branch`，创建第一个 root task
- `storage_snapshot` 初始化为 `{}`

### 7.2 用户发消息时 — `POST /send_message`

文件：`api/app/chat/send_message.py` → `send_message()`

```
用户发送消息 → get_or_create_pending_task(session_id, user_id, branch_name)
```

- 如果分支 leaf task 状态为 `pending` → 复用，**不创建**新 task
- 如果 leaf task 已处理完 → **追加新 task**，从祖先继承 `storage_snapshot`
- 如果分支不存在 → 抛异常（`send_message` 要求会话已存在）

### 7.3 修改工具启用状态 — `UpdateToolsStatusCommand`

文件：`api/app/chat/session_agent_config/command/update_tools_status/command.py`

```
修改工具状态 → get_or_create_pending_task → 获取 pending task → 写入 overlay
```

- 先通过 `get_or_create_pending_task` 确保 pending task 存在
- 在分布式锁保护下读取 `storage_snapshot`，将工具配置写入 `session_config_overlay` key

### 7.4 修改 MCP 配置 — `UpdateMcpServersConfigCommand`

文件：`api/app/chat/session_agent_config/command/update_mcp_servers_config/command.py`

```
修改 MCP 配置 → get_or_create_pending_task → 获取 pending task → 写入 overlay
```

- 与修改工具状态同模式，overlay 写入 `mcp_config` 部分

### 7.5 查询工具状态 — `GetToolsStatusCommand`

文件：`api/app/chat/session_agent_config/command/get_tools_status/command.py`

```
查询工具状态 → get_or_create_pending_task → 读取 storage_snapshot → 合并 overlay
```

- **读操作**，但通过 `get_or_create_pending_task` 间接保证 pending task 存在
- 如果 leaf task 不为 pending 则会创建新 task，从而可能间接触发 `storage_snapshot` 继承

### 7.6 查询 MCP 配置 — `GetMcpServersConfigCommand`

文件：`api/app/chat/session_agent_config/command/get_mcp_servers_config/command.py`

```
查询 MCP 配置 → get_or_create_pending_task → 读取 storage_snapshot → 合并 overlay
```

- 与查询工具状态同模式

### 7.7 测试 MCP 连接 — `TestMcpConnectionCommand`

文件：`api/app/chat/session_agent_config/command/test_mcp_connection/command.py`

```
测试 MCP 连接 → get_or_create_pending_task → 读取 storage_snapshot → 合并 overlay → 测试连接
```

- 同上模式，确保 pending task 存在后读取配置，再测试实际的 MCP 连接

### 7.8 消息处理入口 — `POST /process_pending_messages`

文件：`api/app/chat/process_pending_messages.py`

```
处理消息 → 获取 leaf task → 检查 storage_snapshot → 读取 overlay → 合并 session_config
```

- **不创建**新 task，而是消费已有的 pending task
- 读取 `storage_snapshot` 中的 `session_config_overlay`，与基础配置深度合并
- 合并后的配置用于初始化工具集和系统提示

### 7.9 创建时机汇总

| 场景 | HTTP 端点 | 底层函数 | 创建新 task? | storage_snapshot 来源 |
|------|-----------|----------|-------------|----------------------|
| 创建会话 | `POST /sessions/create` | `create_root_task_with_branch` | 是（root） | `{}`（空 dict） |
| 发消息 | `POST /send_message` | `get_or_create_pending_task` | 可能 | 继承祖先 / 复用 |
| 修改工具状态 | config 命令 | `get_or_create_pending_task` | 可能 | 继承祖先 / 复用 |
| 修改 MCP 配置 | config 命令 | `get_or_create_pending_task` | 可能 | 继承祖先 / 复用 |
| 查询工具状态 | config 命令 | `get_or_create_pending_task` | 可能 | 继承祖先 / 复用 |
| 查询 MCP 配置 | config 命令 | `get_or_create_pending_task` | 可能 | 继承祖先 / 复用 |
| 测试 MCP 连接 | config 命令 | `get_or_create_pending_task` | 可能 | 继承祖先 / 复用 |
| 处理消息 | `POST /process_pending_messages` | 无（使用已有 task） | 否 | 读取现有 |

**关键模式**：除了会话创建（root task），其余所有业务场景都通过 `get_or_create_pending_task` 这个统一入口。该函数的行为是：

```
查找分支 → leaf task 状态 == pending ?
  ├─ 是 → 复用该 task（storage_snapshot 不变）
  └─ 否 → 追加新 task（继承祖先 storage_snapshot）
```

这意味着：**任何 config 命令或发消息操作，都可能因为 leaf task 已处理而间接触发新 task 创建和 storage_snapshot 继承**。

---

## 9. 涉及文件清单

### 数据库层
| 文件 | 说明 |
|------|------|
| `api/chat/sql_stat/u2a_session_task/U2ASessionTask.sql` | SQL 定义 |
| `api/chat/sql_stat/u2a_session_task/utils.py` | Python CRUD 函数 |
| `api/chat/sql_stat/u2a_session_branch_task/operations.py` | 分支/任务创建（含快照继承） |

### 工具使用者
| 文件 | 说明 |
|------|------|
| `api/agent/tools/todo/storage_backend/storage_snapshot.py` | Todo 存储后端 |
| `api/agent/tools/todo/storage_backend/__init__.py` | 后端导出 |
| `api/agent/tools/todo/constructor.py` | Todo 工具构造器 |
| `api/agent/tools/todo/config_data_model.py` | Todo 配置（storage_backend 选项） |
| `api/agent/tools/skills/load_skill/constructor.py` | Skill 加载工具 |
| `api/agent/tools/skills/data_model.py` | Skill 数据模型 + key 常量 |

### 会话配置
| 文件 | 说明 |
|------|------|
| `api/agent/session_agent_config/constants.py` | overlay key 常量 |
| `api/agent/session_agent_config/crud.py` | 配置读写（含 overlay 合并） |
| `api/app/chat/session_agent_config/command/update_tools_status/command.py` | 工具状态覆盖 |
| `api/app/chat/session_agent_config/command/update_mcp_servers_config/command.py` | MCP 配置覆盖 |

### 并发控制
| 文件 | 说明 |
|------|------|
| `api/redis/lock_names.py` | 锁名定义 |
| `docs/for_LLM_dev/分布式锁使用规范.md` | 分布式锁使用规范 |

### 业务入口
| 文件 | 说明 |
|------|------|
| `api/app/chat/process_pending_messages.py` | 消息处理主入口（读取 overlay 生效配置） |
