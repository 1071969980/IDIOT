# 01 全局概览

## 信息流总图

```
┌─────────────────────────────────────────────────────────────────────┐
│                     process_pending_messages                        │
│                   (api/app/chat/process_pending_messages.py)         │
│                                                                     │
│  ① Session Config ──→ ② System Prompt ──→ ③ Tools Init ──┐        │
│  ④ User Messages ──────────────────────────────────────────┤        │
│  ⑤ Storage Snapshot Overlay ──────────────────────────────┤        │
└─────────────────────────────────────────────────────────────┼───────┘
                                                              │
                                                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        session_chat_task                            │
│                      (api/chat/chat_task.py)                        │
│                                                                     │
│  ⑥ Short-term Memory (历史消息) ─────────────────────────┐        │
│  ⑦ Pending User Messages (当前用户消息) ──────────────────┤        │
└─────────────────────────────────────────────────────────────┼───────┘
                                                              │
                                                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   main_agent_strategy (三阶段)                      │
│              (api/agent/strategy/main_agent_strategy.py)             │
│                                                                     │
│  Phase 1: Memory Recall (条件触发) ──→ ⑧ Memory Recall 结果       │
│  Phase 2: Main Agent 执行                                           │
│  Phase 3: Memory Write (后台任务)                                    │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         MainAgent (运行时)                           │
│                    (api/agent/base_agent.py)                         │
│                                                                     │
│  ┌─ 上下文组装 ─────────────────────────────────────────────┐      │
│  │  [System Prompt]                                        │      │
│  │  [Memory Trails: 历史消息 (含 context breakpoint 截断)]   │      │
│  │  [运行时注入: 提醒、TODO、摘要压缩 ...]                    │      │
│  │  [Tool Definitions]                                     │      │
│  └─────────────────────────────────────────────────────────┘      │
│                              │                                      │
│                      LLM API Call                                  │
│                              │                                      │
│  ┌─ 迭代循环 ───────────────────────────────────────────────┐     │
│  │  Assistant Response → Tool Calls → Tool Results → 循环    │     │
│  └─────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────┘
```

## 信息流阶段划分

### 阶段一：预处理（process_pending_messages）

在创建 Agent 之前，`process_pending_messages` 收集并验证以下信息：

| 序号 | 信息 | 来源文件 | 数据类型 | 文档章节 |
|------|------|----------|----------|----------|
| ① | 会话配置 | `session_agent_config/crud.py` | `SessionAgentConfig` | [07_session_config](./07_session_config.md) |
| ② | 系统提示词 | `chat/render_system_prompt.py` | `str` | [02_system_prompt](./02_system_prompt_chain.md) |
| ③ | 工具初始化 | `chat/tool_init.py` | `ToolInitializationResult` | [03_tool_definitions](./03_tool_definitions.md) |
| ④ | 待处理用户消息 | `u2a_user_msg/utils.py` | `list[UserMessage]` | [04_memory_and_history](./04_memory_and_history.md) |
| ⑤ | Storage Snapshot 覆盖层 | `u2a_session_task` 表 | `dict` | [07_session_config](./07_session_config.md) |

### 阶段二：任务初始化（session_chat_task）

`session_chat_task` 将预处理信息与历史消息合并：

| 序号 | 信息 | 来源文件 | 数据类型 | 文档章节 |
|------|------|----------|----------|----------|
| ⑥ | 短期记忆（历史） | `u2a_user_short_term_memory` + `u2a_agent_short_term_memory` | `list[ChatCompletionMessageParam]` | [04_memory_and_history](./04_memory_and_history.md) |
| ⑦ | 当前用户消息 | 阶段一的 pending_messages | `list[ChatCompletionUserMessageParam]` | [04_memory_and_history](./04_memory_and_history.md) |

### 阶段三：Agent 执行（main_agent_strategy + MainAgent）

Agent 运行期间，以下信息动态注入上下文：

| 序号 | 信息 | 来源文件 | 注入时机 | 文档章节 |
|------|------|----------|----------|----------|
| ⑧ | 记忆召回结果 | `agent/strategy/main_agent_strategy.py` | Phase 1 条件触发 | [04_memory_and_history](./04_memory_and_history.md) |
| ⑨ | TODO 列表 | `agent/tools/todo/lifecycle_hooks.py` | agent_start / iteration_end | [05_runtime_injections](./05_runtime_injections.md) |
| ⑩ | 系统提醒（工具状态等） | `agent/system_reminder/` | agent_start | [05_runtime_injections](./05_runtime_injections.md) |
| ⑪ | 摘要压缩引导 | `agent/tools/summarization_compact/lifecycle_hooks.py` | iteration_end | [05_runtime_injections](./05_runtime_injections.md) |
| ⑫ | 工具执行结果 | 各 tool constructor | 迭代循环中 | [03_tool_definitions](./03_tool_definitions.md) |

### 阶段四：最终组装（base_agent）

将所有信息组装为 LLM API 的 messages 参数：

```python
# base_agent.py:288-289
mem = [self._system_mem] if self._system_mem else []  # System Prompt
mem += self._memory_trails.get_marker_linear_memories(mem_marker_name)  # 历史消息
```

详见 [06_message_assembly](./06_message_assembly.md)。

## 关键入口文件索引

| 文件路径 | 角色 |
|----------|------|
| `api/app/chat/process_pending_messages.py` | HTTP 入口，收集预处理信息 |
| `api/chat/chat_task.py` | 会话任务，组装历史消息并启动 Agent |
| `api/chat/render_system_prompt.py` | 系统提示词渲染引擎 |
| `api/chat/tool_init.py` | 工具初始化入口 |
| `api/agent/strategy/main_agent_strategy.py` | Agent 三阶段策略 |
| `api/agent/base_agent.py` | Agent 基类，消息组装与 LLM 调用 |
| `api/agent/memory_trails/trails.py` | 内存中的链式消息管理 |
| `api/agent/session_agent_config/config_data_model.py` | 会话配置数据模型 |
