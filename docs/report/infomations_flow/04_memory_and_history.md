# 04 记忆系统与历史消息

## 概述

Agent 的上下文中，除了系统提示词和工具定义，最大的文本来源是对话历史。这些历史通过「短期记忆」从数据库加载，以「Memory Trails」链表结构在内存中管理，并在运行时动态追加新消息。

## 记忆系统架构

```
┌─────────────────────────────────────────────────┐
│               数据库持久化层                      │
│                                                   │
│  u2a_user_short_term_memory    (用户消息)         │
│  u2a_agent_short_term_memory   (Agent消息+工具)   │
└─────────────────────────────────────────────────┘
                    │
                    ▼ query_short_term_memory()
┌─────────────────────────────────────────────────┐
│              Memory Trails (内存层)               │
│                                                   │
│  链表结构: MemoryNode → MemoryNode → ...          │
│  命名标记: "base", "major", "mem_recall:xxx"     │
│  Context Breakpoint 机制控制发送给 LLM 的长度     │
└─────────────────────────────────────────────────┘
                    │
                    ▼ get_marker_linear_memories()
┌─────────────────────────────────────────────────┐
│              LLM API messages 参数               │
│                                                   │
│  [system_msg, user_msg, assistant_msg, tool_msg,  │
│   user_msg, assistant_msg, ...]                   │
└─────────────────────────────────────────────────┘
```

## 一、短期记忆加载

### 入口

**文件**: `api/chat/chat_task.py`

```python
# 行 271
memories = await query_short_term_memory(session_task_id=session_task_id)
```

### 数据来源

两个数据库表：

| 表名 | 存储内容 | 角色 (role) | 排序字段 |
|------|----------|-------------|----------|
| `u2a_user_short_term_memory` | 用户消息 | `"user"` | `seq_in_session` (外), `seq_index` (内) |
| `u2a_agent_short_term_memory` | Agent 响应、工具调用、工具结果 | `"assistant"`, `"tool"` | `seq_in_session` (外), `sub_seq_index` (内) |

### 查询工具函数

| 函数 | 文件 |
|------|------|
| `query_short_term_memory()` | `api/chat/chat_task.py` |
| 用户消息查询 | `api/chat/sql_stat/u2a_user_short_term_memory/utils.py` |
| Agent 消息查询 | `api/chat/sql_stat/u2a_agent_short_term_memory/utils.py` |

### Context Breakpoint 截断

加载历史时，若存在 `context_breakpoint`，则截断 breakpoint 之前的消息，仅保留 breakpoint 及之后的消息。

## 二、Memory Trails 系统

### 数据结构

**文件**: `api/agent/memory_trails/`

#### MemoryNode

```python
@dataclass
class MemoryNode:
    id: UUID                                 # 唯一 ID
    content: ChatCompletionMessageParam       # 消息内容
    prev_id: UUID | None                     # 前驱节点
    is_new: bool = False                     # 是否新建（需要持久化）
    is_context_breakpoint: bool = False      # 上下文截断点
    tool_task_result: ToolTaskResult | None  # 关联的工具执行结果
    tool_name: str | None                    # 工具名
    to_agent_msg: bool = False               # 是否存储到 Agent 消息表
```

#### MemoryTrails

```python
class MemoryTrails:
    _nodes: dict[UUID, MemoryNode]    # 节点字典
    _markers: dict[str, UUID]         # 标记名 → 叶节点 ID
```

链表结构，每个标记指向链表的一个叶节点。

### 核心操作

| 方法 | 说明 |
|------|------|
| `create_marker(name, memories)` | 创建标记并初始化消息链 |
| `fork_marker(source, target)` | 从源标记分叉出新标记 |
| `append_to_marker(name, msg)` | 向标记追加消息 |
| `extend_to_marker(name, msgs)` | 向标记追加多条消息 |
| `get_marker_linear_memories(name)` | 获取标记的线性消息列表（含截断处理） |
| `get_new_nodes(name)` | 获取标记下的新建节点 |
| `extract_db_create_data(name, ...)` | 提取需持久化的数据 |

### 标记命名约定

| 标记名 | 用途 |
|--------|------|
| `"base"` | 基础标记，包含初始加载的历史消息 |
| `"major"` | 主标记，从 base 分叉，MainAgent 在此标记上工作 |
| `"mem_recall:{uuid}"` | 记忆召回标记，MemRecallAgent 的工作区 |
| `"mem_write:{uuid}"` | 记忆写入标记，MemWriteAgent 的工作区 |

### 三阶段中的使用

**文件**: `api/agent/strategy/main_agent_strategy.py`

```
Phase 1: Memory Recall (条件触发)
  trails.create_marker("base", memories)
  trails.fork_marker("base", "major")
  trails.fork_marker("base", f"mem_recall:{uuid}")
  → MemRecallAgent 在 mem_recall 标记上追加召回结果
  → 召回结果合并到 major 标记

Phase 2: Main Agent
  MainAgent 使用 "major" 标记
  → get_marker_linear_memories("major") 获取完整上下文

Phase 3: Memory Write (后台)
  trails.fork_marker("major", f"mem_write:{uuid}")
  → MemWriteAgent 在 mem_write 标记上工作
```

## 三、用户消息

### 待处理消息（当前轮次）

**来源**: `process_pending_messages.py:124-128`

```python
pending_messages = [
    msg for msg in all_task_messages
    if msg.status == "waiting_agent_ack_user"
]
```

这些消息在 `session_chat_task` 中转换为 `ChatCompletionUserMessageParam`：

```python
# chat_task.py:277-283
new_user_mem = [
    ChatCompletionUserMessageParam(
        content=msg.content,
        role="user",
    )
    for msg in pending_messages_sorted
]
```

### 投递消息（外部注入）

**文件**: `api/agent/tools/feed_message/constructor.py`

通过 `feed_message` 工具，外部消息可以以 `role="system"` 的形式注入 Agent 上下文：

```
ChatCompletionSystemMessageParam(
    content=f"{EXTERNAL_MESSAGE_BLOCK_START}\n{message}\n{EXTERNAL_MESSAGE_BLOCK_END}",
    role="system"
)
```

## 四、记忆召回

### 条件触发

**文件**: `api/agent/strategy/main_agent_strategy.py`

当 `_has_valid_memory_indices()` 返回 True 时，启动 MemRecallAgent 进行记忆召回。

### 召回结果格式

```
<memory_recall>
  [召回的记忆内容]
</memory_recall>
```

以 `role="system"` 消息追加到 Memory Trails。

### 失败降级

若记忆召回失败，注入降级提示：

```python
ChatCompletionSystemMessageParam(
    content="记忆召回不可用，请继续执行当前任务。",
    role="system"
)
```

## 消息角色汇总

| role | 来源 | 说明 |
|------|------|------|
| `"system"` | 系统提示词、运行时注入、记忆召回 | 系统级指令 |
| `"user"` | 用户消息 | 用户输入 |
| `"assistant"` | LLM 响应 | 包含 content 和可选 tool_calls |
| `"tool"` | 工具执行结果 | 包含 tool_call_id |

## 相关文件索引

| 文件 | 职责 |
|------|------|
| `api/chat/chat_task.py` | 记忆加载与消息组装 |
| `api/agent/memory_trails/trails.py` | Memory Trails 核心实现 |
| `api/agent/memory_trails/node.py` | MemoryNode 定义 |
| `api/chat/sql_stat/u2a_user_short_term_memory/utils.py` | 用户短期记忆查询 |
| `api/chat/sql_stat/u2a_agent_short_term_memory/utils.py` | Agent 短期记忆查询 |
| `api/agent/strategy/main_agent_strategy.py` | 三阶段策略与记忆召回 |
| `api/agent/tools/feed_message/constructor.py` | 外部消息注入 |
