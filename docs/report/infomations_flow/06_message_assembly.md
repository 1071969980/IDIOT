# 06 最终消息组装

## 概述

本文档描述所有信息如何最终组装为 LLM API 调用的 `messages` 参数，以及迭代循环中新消息如何追加。

## 最终组装位置

**文件**: `api/agent/base_agent.py`

```python
# 行 288-289
mem = [self._system_mem] if self._system_mem else []
mem += self._memory_trails.get_marker_linear_memories(mem_marker_name)
```

这是每次 LLM 调用前的消息组装，仅两步：
1. 加入系统提示词（如果存在）
2. 加入 Memory Trails 中指定标记的线性消息列表

## 消息组装的完整时间线

### T0: process_pending_messages 阶段

```
输入:
  - Session Config (含 system_prompt_config, tools_config, mcp_config)
  - Storage Snapshot Overlay
  - Pending User Messages
  - Branch / Task 信息

输出:
  - system_prompt: str
  - tool_init_res: ToolInitializationResult
  - mcp_tools_loader: McpToolsLoader
  - pending_messages: list[UserMessage]
```

### T1: session_chat_task 阶段

**文件**: `api/chat/chat_task.py`

```
输入:
  - system_prompt (来自 T0)
  - tool_init_res (来自 T0)
  - pending_messages (来自 T0)
  - session_task_id

步骤:
  1. 查询短期记忆: memories = query_short_term_memory(session_task_id)
  2. 转换用户消息: new_user_mem = [ChatCompletionUserMessageParam(...) for msg in pending_messages]
  3. 创建 Memory Trails:
     - trails.create_marker("base", memories + new_user_mem)
  4. 创建 MainAgent:
     - system_mem = ChatCompletionSystemMessageParam(content=system_prompt, role="system")
     - 传入 trails, tool_init_res 等
```

### T2: main_agent_strategy 三阶段

**文件**: `api/agent/strategy/main_agent_strategy.py`

```
Phase 1: Memory Recall (条件触发)
  trails.fork_marker("base", "major")
  trails.fork_marker("base", f"mem_recall:{uuid}")
  → MemRecallAgent 执行，召回结果追加到 mem_recall 标记
  → 召回结果合并到 major 标记

Phase 2: Main Agent
  MainAgent 使用 "major" 标记
  → 运行 on_agent_start hooks (注入提醒、TODO 等)
  → 进入迭代循环

Phase 3: Memory Write (后台)
  → MemWriteAgent 在 "mem_write" 标记上工作
```

### T3: MainAgent 迭代循环

**文件**: `api/agent/base_agent.py`

```
while True:
    ① 组装消息:
       mem = [system_mem] + trails.get_marker_linear_memories("major")

    ② 准备工具参数:
       tools = prepare_tool_params()  # → list[ChatCompletionToolParam]

    ③ 调用 LLM API:
       generation_delegate_for_async_openai(
           messages=mem,
           tools=tools,  # 可选
           stream=True,
           ...
       )

    ④ 处理响应:
       if finish_reason == "stop":
           → 退出循环
       if finish_reason == "tool_calls":
           → 执行工具 → 追加结果到 trails → 继续循环

    ⑤ on_iteration_end hooks:
       → 注入摘要压缩引导等
```

## 消息格式示例

### 最终发送给 LLM 的 messages 列表

```python
[
    # 系统提示词
    {"role": "system", "content": "你是一个智能助手..."},

    # 历史用户消息 (从短期记忆加载)
    {"role": "user", "content": "帮我分析这段代码"},

    # 历史 Agent 响应
    {"role": "assistant", "content": "好的，让我看看...",
     "tool_calls": [{"id": "call_xxx", "function": {"name": "read_file", "arguments": "..."}}]},

    # 历史工具结果
    {"role": "tool", "tool_call_id": "call_xxx", "content": "     1→ import os\n     2→ ..."},

    # 历史 Agent 后续响应
    {"role": "assistant", "content": "这段代码的功能是..."},

    # 运行时注入 (如 TODO 列表)
    {"role": "system", "content": "<todo_list>\n- [pending] 分析代码\n- [completed] 读取文件\n</todo_list>"},

    # 当前用户消息
    {"role": "user", "content": "继续分析"},
]
```

### 工具参数 (tools)

```python
[
    {"type": "function", "function": {
        "name": "read_file",
        "description": "读取文件内容...",
        "parameters": {"type": "object", "properties": {...}}
    }},
    {"type": "function", "function": {
        "name": "bash",
        "description": "执行命令...",
        "parameters": {"type": "object", "properties": {...}}
    }},
    # ... 更多工具
]
```

## Context Breakpoint 机制

`get_marker_linear_memories()` 中的截断逻辑：

```
链表: [node_0] → [node_1] → [node_2_BP] → [node_3] → [node_4]
                                     ↑ context breakpoint

截断后返回: [node_2_BP, node_3, node_4]
```

截断点之前的消息不再发送给 LLM，用于控制上下文长度。

## 迭代中消息追加

### Assistant 响应追加

```python
# base_agent.py - on_create_assistant_memory()
msg = ChatCompletionAssistantMessageParam(
    content=response_content,
    role="assistant",
    tool_calls=tool_calls,  # 可选
)
self._memory_trails.append_to_marker(mem_marker_name, msg)
```

### 工具结果追加

```python
# base_agent.py - 工具执行后
tool_mem = ChatCompletionToolMessageParam(
    content=tool_result.str_content,
    role="tool",
    tool_call_id=tool_call_id,
)
self._memory_trails.extend_to_marker(mem_marker_name, [tool_mem])
```

### 运行时注入追加

所有 lifecycle hook 通过 `append_to_marker` 追加 `role="system"` 消息。

## 数据流全景

```
┌───────────────────────────────────────────────────────────────────┐
│                         数据来源层                                 │
│                                                                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │Session   │ │LangFuse/ │ │Database  │ │User      │            │
│  │Config DB │ │Jinja/Var │ │Short-term│ │Messages  │            │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘            │
│       │            │            │            │                    │
└───────┼────────────┼────────────┼────────────┼────────────────────┘
        │            │            │            │
        ▼            ▼            ▼            ▼
┌───────────────────────────────────────────────────────────────────┐
│                       预处理层                                    │
│                                                                   │
│  render_system_prompt()  init_tools()  query_short_term_memory() │
│        │                     │                │                   │
│        ▼                     ▼                ▼                   │
│  system_prompt: str    ToolInitResult    list[MessageParam]       │
│                                                │                  │
└────────────────────────────────────────────────┼──────────────────┘
                                                 │
                                                 ▼
┌───────────────────────────────────────────────────────────────────┐
│                    Memory Trails 层                                │
│                                                                   │
│  create_marker("base", memories + new_user_messages)             │
│  fork_marker("base", "major")                                    │
│                                                                   │
│  [system_prompt注入] → Agent._system_mem                         │
│  [运行时hooks注入] → trails.append_to_marker("major", ...)       │
│  [工具结果注入]   → trails.append_to_marker("major", ...)       │
│  [Agent响应注入]  → trails.append_to_marker("major", ...)       │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
                                                 │
                                                 ▼
┌───────────────────────────────────────────────────────────────────┐
│                    LLM API 调用层                                  │
│                                                                   │
│  messages = [system_mem] + trails.get_marker_linear_memories()   │
│  tools = prepare_tool_params()                                    │
│                                                                   │
│  generation_delegate_for_async_openai(messages=messages,          │
│                                       tools=tools,                │
│                                       stream=True)                │
└───────────────────────────────────────────────────────────────────┘
```

## 相关文件索引

| 文件 | 职责 |
|------|------|
| `api/agent/base_agent.py` | 消息组装、LLM 调用、迭代循环 |
| `api/agent/strategy/main_agent_strategy.py` | 三阶段策略编排 |
| `api/chat/chat_task.py` | 任务初始化、记忆加载 |
| `api/agent/memory_trails/trails.py` | Memory Trails 管理 |
| `api/llm/generator.py` | LLM 生成函数 |
| `api/load_balance/delegate/openai.py` | OpenAI API 调用代理 |
