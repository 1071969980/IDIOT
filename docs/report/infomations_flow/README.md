# 流向 Agent 的文本信息地图

本文档集描述了 IDIOT 项目中所有可能流向 Agent（LLM）上下文的文本信息来源、流转路径和组装方式。

## 文档结构

| 文件 | 内容 |
|------|------|
| [01_overview.md](./01_overview.md) | 全局概览：信息流总图与阶段划分 |
| [02_system_prompt_chain.md](./02_system_prompt_chain.md) | 系统提示词渲染链 |
| [03_tool_definitions.md](./03_tool_definitions.md) | 工具定义文本流 |
| [04_memory_and_history.md](./04_memory_and_history.md) | 记忆系统与历史消息 |
| [05_runtime_injections.md](./05_runtime_injections.md) | 运行时注入（提醒、TODO、摘要压缩等） |
| [06_message_assembly.md](./06_message_assembly.md) | 最终消息组装：发送给 LLM 的完整上下文 |
| [07_session_config.md](./07_session_config.md) | 会话配置系统与覆盖机制 |

## 起点文件

本研究以 `api/app/chat/process_pending_messages.py` 为入口，追踪至 `api/chat/chat_task.py` → `api/agent/strategy/main_agent_strategy.py` → `api/agent/base_agent.py` 这条主线，逐步展开所有信息源。

## 术语约定

- **Agent**：指执行 LLM 调用的代理实例（MainAgent、SubAgent 等）
- **上下文/Context**：发送给 LLM API 的消息列表（messages 参数）
- **Memory Trails**：内存中的链表结构，管理对话历史
- **Marker**：Memory Trails 中的命名标记，用于区分不同的消息分支
- **Context Breakpoint**：上下文截断点，用于控制发送给 LLM 的历史长度
