# 05 运行时注入

## 概述

在 Agent 执行期间，除了初始的系统提示词和历史消息外，还有多种文本通过 lifecycle hook 机制动态注入到 Agent 的上下文中。这些注入不修改核心 Agent 代码，而是通过装饰器模式在特定时机插入。

## Lifecycle Hook 机制

### 装饰器系统

**文件**: （lifecycle hook 装饰器定义）

| 装饰器 | 说明 |
|--------|------|
| `@lifecycle_hook(method_name, position)` | 定义单个 hook |
| `@agent_decorator(*hooks)` | 将多个 hook 绑定到 Agent 类 |

### Hook 时机

| 时机 | 说明 |
|------|------|
| `on_agent_start` | Agent 开始执行前 |
| `on_iteration_end` | 每轮迭代结束后 |
| `prepare_tool_closures` | 准备工具闭包时 |
| `prepare_tool_params` | 准备工具参数时 |

### position

| 值 | 说明 |
|----|------|
| `"before"` | 在目标方法前执行 |
| `"after"` | 在目标方法后执行 |

### MainAgent 的装饰器堆叠

```python
@agent_decorator(inject_todo_context_on_agent_start,
                 inject_todo_context_on_iteration_end)
@agent_decorator(inject_summarization_compact_context,
                 inject_summarization_compact_closure)
@agent_decorator(inject_tool_enable_status_reminder,
                 inject_mcp_server_config_changed_reminder,
                 inject_branch_changed_reminder)
class MainAgent(AgentBase):
    ...
```

---

## 一、系统提醒（System Reminder）

### 1.1 工具启用状态提醒

**文件**: `api/agent/system_reminder/tool_enable_status/decorators.py`

| 属性 | 值 |
|------|-----|
| Hook | `on_agent_start`, position=`before` |
| 控制标记 | `TO_REMINDER_TOOL_ENABLE_STATUS_MARK_NAME` |
| XML 包裹 | `<system_reminder>...</system_reminder>` |

**内容**: 列出当前显式可用的工具名称，提醒 Agent 仅使用授权工具。

### 1.2 MCP 服务器配置变更提醒

**文件**: `api/agent/system_reminder/` (同目录)

| 属性 | 值 |
|------|-----|
| Hook | `on_agent_start`, position=`before` |
| 控制标记 | `TO_REMINDER_MCP_SERVER_CONFIG_CHANGED_MARK_NAME` |
| XML 包裹 | `<system_reminder>...</system_reminder>` |

**内容**: 通知 MCP 服务器配置已变更，建议重新发现工具。

### 1.3 分支变更提醒

**文件**: `api/agent/system_reminder/branch_changed/decorators.py`

| 属性 | 值 |
|------|-----|
| Hook | `on_agent_start`, position=`before` |
| 控制标记 | `TO_REMINDER_BRANCH_CHANGED_MARK_NAME` |
| XML 包裹 | `<system_reminder>...</system_reminder>` |

**内容**: 通知当前会话任务分支已变更。

### 控制机制

所有提醒在注入前检查 session_task 的 logic_marks 字段：

```
session_task.logic_marks
    │
    ├── TO_REMINDER_TOOL_ENABLE_STATUS_MARK_NAME == True ?
    │     └── 是 → 注入工具启用状态提醒
    ├── TO_REMINDER_MCP_SERVER_CONFIG_CHANGED_MARK_NAME == True ?
    │     └── 是 → 注入 MCP 变更提醒
    └── TO_REMINDER_BRANCH_CHANGED_MARK_NAME == True ?
          └── 是 → 注入分支变更提醒
```

---

## 二、TODO 列表上下文注入

**文件**: `api/agent/tools/todo/lifecycle_hooks.py`

### 两个 Hook

| Hook | 时机 | 触发条件 |
|------|------|----------|
| `inject_todo_context_on_agent_start` | `on_agent_start` | TODO 工具已加载 |
| `inject_todo_context_on_iteration_end` | `on_iteration_end` | 刚执行了 todo_write 工具 |

### 格式

```
<todo_list>
  [按状态分组的 TODO 列表]
</todo_list>
```

### 内容结构

- 按 pending/completed 分组
- 组内按优先级排序
- 以 `role="system"` 消息注入

---

## 三、摘要压缩引导

**文件**: `api/agent/tools/summarization_compact/lifecycle_hooks.py`

### Hook

| Hook | 时机 |
|------|------|
| `inject_summarization_compact_context` | `on_iteration_end` |
| `inject_summarization_compact_closure` | `prepare_tool_closures` |

### 触发级别

根据 token 使用量，分为三个级别：

| 级别 | 行为 |
|------|------|
| `"no"` | 不注入 |
| `"suggest"` | 建议压缩，注入压缩引导 |
| `"must"` | 强制压缩，注入强制压缩指令 |

### 注入内容

- 压缩指令文本
- 压缩引导（应包含/排除哪些内容）
- 工具参数公开信息

### XML 包裹

使用 `<system_reminder>...</system_reminder>` 包裹。

---

## 四、记忆写入上下文注入

**文件**: `api/agent/tools/memory_write/lifecycle_hooks.py`

为 MemWriteAgent 注入：

| 注入内容 | 说明 |
|----------|------|
| 记忆类型定义 | 可用的记忆分类 |
| 目录范围 | JuiceFS 中可操作的目录 |
| 工作要求 | 写入规范 |

同时启用 read/write 工具和 bash。

---

## 五、记忆召回上下文注入

**文件**: `api/agent/tools/memory_recall/lifecycle_hooks.py`

为 MemRecallAgent 注入：

| 注入内容 | 说明 |
|----------|------|
| 召回要求 | 需要召回什么类型的记忆 |
| MEMORY.md 索引 | 可用的记忆索引文件 |

同时启用只读工具和 return_memory_recall 工具。

---

## 六、工具选择引导（Tool Choice Steering）

**文件**: `api/agent/base_agent.py`

当 `_tool_choice_steering` 激活时，若 Agent 尝试停止但应继续调用工具：

```python
# 行 387-398
msg = ChatCompletionSystemMessageParam(
    content=f"{SYS_REMINDER_BLOCK_START}...{SYS_REMINDER_BLOCK_END}",
    role="system"
)
self._memory_trails.append_to_marker(mem_marker_name, msg)
```

**内容**: 引导 Agent 使用指定工具集中的工具。

---

## 注入时机汇总

```
Agent 启动
  │
  ├── [on_agent_start / before]
  │     ├── 工具启用状态提醒 (条件: logic_mark)
  │     ├── MCP 配置变更提醒 (条件: logic_mark)
  │     ├── 分支变更提醒 (条件: logic_mark)
  │     └── TODO 列表上下文 (条件: TODO 工具已加载)
  │
  ▼
  迭代循环
  │
  ├── LLM 调用
  ├── 工具执行
  ├── [on_iteration_end]
  │     ├── TODO 列表更新 (条件: 执行了 todo_write)
  │     └── 摘要压缩引导 (条件: token 超阈值)
  │
  ├── [条件: tool_choice_steering]
  │     └── 工具选择引导
  │
  └── → 下一轮迭代 或 结束
```

## XML 标记定义

**文件**: `api/agent/xml_marks_def.py`

| 标记 | 用途 |
|------|------|
| `<system_reminder>` | 系统提醒（通用） |
| `<todo_list>` | TODO 列表 |
| `<memory_recall>` | 记忆召回结果 |
| `<tool_discovery_res>` | 工具发现结果 |
| `<external_message>` | 外部投递消息 |

## 相关文件索引

| 文件 | 职责 |
|------|------|
| `api/agent/system_reminder/tool_enable_status/decorators.py` | 工具状态提醒 |
| `api/agent/system_reminder/branch_changed/decorators.py` | 分支变更提醒 |
| `api/agent/tools/todo/lifecycle_hooks.py` | TODO 注入 |
| `api/agent/tools/summarization_compact/lifecycle_hooks.py` | 摘要压缩引导 |
| `api/agent/tools/memory_write/lifecycle_hooks.py` | 记忆写入注入 |
| `api/agent/tools/memory_recall/lifecycle_hooks.py` | 记忆召回注入 |
| `api/agent/tools/feed_message/constructor.py` | 外部消息投递 |
| `api/agent/base_agent.py` | 工具选择引导 |
| `api/agent/xml_marks_def.py` | XML 标记常量 |
