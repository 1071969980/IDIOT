# 角色对话策略更新功能 - 日志记录规范

---
文档标题：background_update_task_spec_implementation
文档描述：本文档描述角色对话策略更新功能的日志记录规范，包括 Span 嵌套层级设计、日志级别使用、Langfuse 元数据附加和关键日志点。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [日志记录规范](#日志记录规范)
    - [Span 嵌套层级设计](#span-嵌套层级设计)
    - [日志级别使用](#日志级别使用)
    - [Langfuse 元数据附加](#langfuse-元数据附加)

## 日志记录规范

### Span 嵌套层级设计

**层级 1：Trace 级别**
- name: `"agent-role-update::background_update_task"`
- metadata: `{user_id, role_name}`

**层级 2：Phase Span**
- phase1: `"agent-role-update::phase1_planning"`
- phase2: `"agent-role-update::phase2_preparation"`
- phase3: `"agent-role-update::phase3_update"`

**层级 3：Agent Span（在 phase3 内部）**
- Agent A: `"agent-role-update::agent_a_execution"`
- Agent B: `"agent-role-update::agent_b_execution"`
- Agent C: `"agent-role-update::agent_c_review"`

**层级 4：循环 Span（在 Agent 内部）**
- 工具调用重试：`"agent-role-update::agent_a_retry_{attempt}"`
- Agent 循环：`"agent-role-update::agent_loop_{loop_count}"`

**Span 嵌套示例代码**:
[查看完整日志记录示例](./examples/logging_example.py)

```python
with logfire.span("agent-role-update::phase3_update"):
    for loop_count in range(MAX_REVIEW_LOOPS):
        with logfire.span("agent-role-update::agent_loop", loop_count=loop_count):
            # Agent A
            for retry_count in range(MAX_TOOL_CALL_RETRIES):
                with logfire.span("agent-role-update::agent_a",
                                retry_count=retry_count) as span:
                    # 执行 Agent A
                    if tool_called:
                        break
                    # 否则重试

            # Agent B
            for retry_count in range(MAX_TOOL_CALL_RETRIES):
                with logfire.span("agent-role-update::agent_b",
                                retry_count=retry_count) as span:
                    # 执行 Agent B
                    if tool_called:
                        break

            # Agent C
            with logfire.span("agent-role-update::agent_c"):
                # 执行 Agent C
                score, suggestions = ...

            # 检查审查结果
            if score >= 80:
                logfire.info("agent-role-update::review_passed", score=score)
                break
            else:
                logfire.info("agent-role-update::review_failed",
                            score=score, suggestions=suggestions)
```

### 日志级别使用

- `logfire.span`: 创建可观测的 span，用于跟踪整个任务流程
- `logfire.info`: 记录正常流程中的关键节点
- `logfire.warning`: 记录非致命错误或可恢复的异常
- `logfire.error`: 记录致命错误和任务终止原因

### Langfuse 元数据附加

参考 `../../../../api/chat/chat_task.py:157-187` 的实现模式：

- 使用 `LangFuseTraceAttributes` 和 `LangFuseSpanAttributes`
- 使用 `logfire.set_baggage()` 设置 trace 级别的上下文

[查看完整的日志记录实现示例](./examples/logging_example.py)

### 关键日志点

1. 任务开始（`task_start`）
2. 每个阶段开始/完成（`phase1_start`, `phase1_complete`, ...）
3. 文件读取成功/失败（`files_read_success`, `files_read_failed`）
4. 文件写入成功/失败（`files_write_success`, `files_write_failed`）
5. Agent 执行开始/完成（`agent_a_start`, `agent_a_complete`, ...）
6. 审查结果（`review_passed`, `review_failed`）
7. 任务完成/失败（`task_complete`, `task_failed`）
8. 缓存回滚（`cache_rollback`）

## 相关实现文档

- [可用的代码基础设施](./01_code_infrastructure.md)
- [文件夹结构设计](./02_folder_structure.md)
- [任务触发规范](./03_task_triggering.md)
- [错误处理规范](./04_error_handling.md)
- [外部容器管理策略](./06_container_management.md)
- [Agent 实现示例](./07_agent_implementations/)
- [上下文文档](../background_update_task_spec_context.md)
- [设计文档](../background_update_task_spec_design.md)
