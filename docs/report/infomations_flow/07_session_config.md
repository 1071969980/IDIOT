# 07 会话配置系统

## 概述

SessionAgentConfig 是控制 Agent 行为的核心配置对象，它决定了系统提示词内容、可用工具、MCP 服务器等多个信息源。配置通过"基础配置 + 覆盖层"的机制支持运行时动态修改。

## SessionAgentConfig 数据模型

**文件**: `api/agent/session_agent_config/config_data_model.py`

```python
class SessionAgentConfig:
    version: SemanticVersion              # 版本号 (major.minor.patch)
    system_prompt_config: SessionSystemPromptConfig  # 系统提示词配置
    tools_config: dict[str, ToolConfigUnion]         # 工具配置字典
    mcp_config: McpConfig                           # MCP 客户端配置
    allowed_rel_dirs_in_juicefs_for_tool: list[str]  # JuiceFS 可访问目录
    user_id_for_scope: UUID | None                   # 作用域用户 ID
```

### 版本兼容性

在 `process_pending_messages.py:148-149` 检查：

```python
if session_config.version.major != DEFAULT_MAIN_AGENT_SESSION_CONFIG.version.major:
    raise ValueError("会话配置版本不兼容")
```

## 配置存储

### 基础配置

**表**: `u2a_session_agent_config`

**文件**: `api/agent/sql_stat/u2a_session_agent_config/utils.py`

| 函数 | 说明 |
|------|------|
| `get_session_config_by_session_id()` | 按 session_id 获取配置行 |
| `update_session_config()` | 更新配置 |

### CRUD 操作

**文件**: `api/agent/session_agent_config/crud.py`

| 函数 | 说明 |
|------|------|
| `get_base_session_config()` | 获取基础配置 |
| `get_effective_session_config()` | 获取生效配置（基础 + 覆盖） |
| `merge_config_overlay()` | 合并覆盖到存储快照 |
| `update_config_overlay()` | 持久化合并后的覆盖 |

## 覆盖层机制

### Storage Snapshot

每个 session_task 有一个 `storage_snapshot` (JSON 字段)，其中可包含 `session_config_overlay` 键。

### 覆盖流程

```
基础配置 (u2a_session_agent_config)
        │
        ▼
SessionAgentConfig.model_validate(base_config)
        │
        ▼
session_config.model_dump(mode="json")
        │                        base_dict
        │                           │
storage_snapshot                    │
    │                               │
    └── "session_config_overlay" ───┤
                                    │
                                    ▼
                          deep_update_dict(base_dict, overlay)
                                    │
                                    ▼
                        SessionAgentConfig.model_validate(merged)
                                    │
                                    ▼
                          最终 SessionAgentConfig
```

**文件**: `process_pending_messages.py:158-164`

```python
if SESSION_CONFIG_OVERLAY_KEY_IN_TASK_STORAGE_SNAPSHOT in task_storage_snapshot:
    session_config_overlay = task_storage_snapshot.get(SESSION_CONFIG_OVERLAY_KEY_IN_TASK_STORAGE_SNAPSHOT, {})
    session_config_base = session_config.model_dump(mode="json")
    session_config_final = deep_update_dict(session_config_base, session_config_overlay)
    session_config = SessionAgentConfig.model_validate(session_config_final)
```

### 常量

**文件**: `api/agent/session_agent_config/constants.py`

```python
SESSION_CONFIG_OVERLAY_KEY_IN_TASK_STORAGE_SNAPSHOT = "session_config_overlay"
```

### deep_update_dict 特殊标记

**文件**: `api/agent/session_agent_config/utils.py`

| 标记 | 说明 |
|------|------|
| `{"$delete": True}` | 从原始 dict 中删除该键 |
| `{"$replace": value}` | 用 value 替换整个值（停止递归） |

## 配置影响的信息流

### system_prompt_config → 系统提示词

详见 [02_system_prompt_chain.md](./02_system_prompt_chain.md)

```
session_config.system_prompt_config
    → render_system_prompt()
    → str (系统提示词)
```

### tools_config → 工具定义

详见 [03_tool_definitions.md](./03_tool_definitions.md)

```
session_config.tools_config
    → init_tools()
    → ToolInitializationResult
    → ChatCompletionToolParam[] (工具定义)
```

### mcp_config → MCP 工具

```
session_config.mcp_config
    → load_mcp_tools()
    → McpToolsLoader
    → ChatCompletionToolParam[] (MCP 工具定义)
```

### allowed_rel_dirs_in_juicefs_for_tool → 工具权限

```
session_config.allowed_rel_dirs_in_juicefs_for_tool
    → init_tools() 参数
    → 限制文件操作工具可访问的目录范围
```

### user_id_for_scope → 工具作用域

```
session_config.user_id_for_scope
    → init_tools() 的 user_id_for_scope 参数
    → 若为空则使用当前用户 ID
```

**文件**: `process_pending_messages.py:186`

```python
user_id_for_scope = session_config.user_id_for_scope or user_id
```

## 默认配置

**文件**: `api/agent/session_agent_config/constants.py`

```python
DEFAULT_MAIN_AGENT_SESSION_CONFIG: SessionAgentConfig
```

包含默认的系统提示词配置（LangFuse "main_agent/system_prompt"）和工具配置（主代理/子代理各自的工具集）。

## Storage Snapshot 的继承

**文件**: `api/chat/sql_stat/u2a_session_task/utils.py`

```
copy_storage_snapshot_from_nearest_ancestor()
```

当新 task 的 storage_snapshot 为 None 时，从最近的祖先 task 复制。

在 `process_pending_messages.py:153-155` 中验证：

```python
if leaf_task.storage_snapshot is None:
    raise ValueError("task storage_snapshot 不存在")
```

## 配置如何影响 Agent 上下文

```
SessionAgentConfig
    │
    ├── system_prompt_config
    │     └── 决定系统提示词文本
    │
    ├── tools_config
    │     ├── 哪些工具启用/禁用 → 决定 tools 参数
    │     ├── 显式/隐式分类 → 显式工具描述进入 LLM 上下文
    │     └── 各工具的配置 → 影响工具行为和输出
    │
    ├── mcp_config
    │     └── MCP 服务器列表 → 动态加载外部工具定义
    │
    ├── allowed_rel_dirs_in_juicefs_for_tool
    │     └── 限制工具的文件系统访问范围
    │
    └── user_id_for_scope
          └── 工具操作的作用域用户
```

## 相关文件索引

| 文件 | 职责 |
|------|------|
| `api/agent/session_agent_config/config_data_model.py` | 数据模型定义 |
| `api/agent/session_agent_config/constants.py` | 默认配置与常量 |
| `api/agent/session_agent_config/crud.py` | CRUD 操作 |
| `api/agent/session_agent_config/utils.py` | deep_update_dict 等工具函数 |
| `api/agent/sql_stat/u2a_session_agent_config/utils.py` | 数据库查询 |
| `api/chat/sql_stat/u2a_session_task/utils.py` | Task/Storage Snapshot 操作 |
