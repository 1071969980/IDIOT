# 角色对话策略更新功能 - 外部容器管理策略

---
文档标题：background_update_task_spec_implementation
文档描述：本文档描述角色对话策略更新功能的外部容器管理策略，包括设计原则、容器定义位置、可变容器设计和容器传递流程。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [外部容器管理策略](#外部容器管理策略)
    - [设计原则](#设计原则)
    - [容器定义位置](#容器定义位置)
    - [可变容器设计](#可变容器设计)

## 外部容器管理策略

### 设计原则

由于 Agent 函数返回 `None`，但调用者需要获取 Agent 的执行结果，因此采用**外部容器**模式：

- **工作容器**：存储 Agent 正在编辑的文件内容（可变容器，由工具闭包捕获并修改）
- **结果容器**：存储 Agent 的执行状态和最终结果（TypedDict，用于后续 Agent 读取）

### 容器定义位置

所有外部容器在 `execute_update_phase()` 函数内部初始化，并通过闭包传递给 Agent 函数和工具回调。

### 可变容器设计

**为什么需要可变容器？**

Python 的闭包无法直接修改外部的不可变对象（如 `str`）。因此，工作变量必须使用可变容器（如 `dict`）包装。

```python
# ❌ 错误：闭包无法修改外部不可变对象
working_strategies = original_strategies  # str 是不可变的

async def callback(param):
    nonlocal working_strategies
    working_strategies = edit_string(...)  # 无法生效

# ✅ 正确：使用可变容器
working_strategies = {"value": original_strategies}  # dict 是可变的

async def callback(param):
    working_strategies["value"] = edit_string(...)  # 可以修改
```

### Agent A 的外部容器

```python
# 工作容器（可变，由工具闭包捕获并直接修改）
agent_a_working_strategies: dict[str, str] = {
    "value": original_strategies  # 初始值为原始策略
}

# 结果容器（TypedDict，用于 Agent B 和 C 读取）
agent_a_result: AgentAResult = {
    "updated_strategies": "",  # Agent 执行完毕后存储最终结果
    "tool_called": False  # 标记是否调用了 edit_strategies 工具
}
```

### Agent B 的外部容器

```python
# 工作容器
agent_b_working_guidance: dict[str, str] = {
    "value": original_guidance  # 初始值为原始指导
}

# 结果容器
agent_b_result: AgentBResult = {
    "updated_guidance": "",
    "tool_called": False
}
```

### Agent C 的外部容器

```python
# Agent C 不需要工作容器，只需要结果容器
agent_c_result: AgentCResult = {
    "score": 0,
    "suggestions": ""
}
```

### 容器传递流程

[查看完整的容器传递流程代码](./examples/container_management_example.py)

**关键代码片段**:

```python
async def execute_update_phase(
    user_id: UUID,
    role_name: str,
    original_strategies: str,
    original_guidance: str,
    strategies_update_list: str
) -> None:
    """第三阶段：更新任务（Agent 循环）"""

    # ========== 初始化所有外部容器 ==========
    agent_a_working_strategies = {"value": original_strategies}
    agent_a_result: AgentAResult = {"updated_strategies": "", "tool_called": False}

    agent_b_working_guidance = {"value": original_guidance}
    agent_b_result: AgentBResult = {"updated_guidance": "", "tool_called": False}

    agent_c_result: AgentCResult = {"score": 0, "suggestions": ""}

    # ========== Agent 循环 ==========
    for loop_count in range(MAX_REVIEW_LOOPS):
        # Agent A 执行
        await run_agent_a_update_strategies(
            original_strategies=original_strategies,
            strategies_update_list=strategies_update_list,
            review_suggestions=agent_c_result["suggestions"] if loop_count > 0 else None,
            service_name="default",
            agent_a_working_strategies=agent_a_working_strategies,  # ← 传递工作容器
            agent_a_result=agent_a_result  # ← 传递结果容器
        )

        # 检查 Agent A 是否成功执行
        if not agent_a_result["tool_called"]:
            raise RuntimeError("Agent A failed to call edit_strategies tool")

        # 提取 Agent A 的最终结果
        agent_a_result["updated_strategies"] = agent_a_working_strategies["value"]

        # Agent B 执行（使用 Agent A 的结果）
        await run_agent_b_update_guidance(
            updated_strategies=agent_a_result["updated_strategies"],
            original_guidance=original_guidance,
            review_suggestions=agent_c_result["suggestions"] if loop_count > 0 else None,
            service_name="default",
            agent_b_working_guidance=agent_b_working_guidance,
            agent_b_result=agent_b_result
        )

        # 检查审查结果
        if agent_c_result["score"] >= REVIEW_PASS_THRESHOLD:
            # 审查通过，写入文件系统
            await write_files_to_filesystem(
                user_id=user_id,
                role_name=role_name,
                strategies=agent_a_result["updated_strategies"],
                guidance=agent_b_result["updated_guidance"]
            )
            break
        # 否则继续下一轮循环
```

### 工具调用检查机制

每个 Agent 函数内部实现重试逻辑：

```python
async def run_agent_a_update_strategies(..., agent_a_result: AgentAResult) -> None:
    # 构造工具...

    # 重试逻辑：最多执行 3 次，直到调用 edit_strategies 工具
    for attempt in range(MAX_TOOL_CALL_RETRIES):
        # 重置工作容器（每次重试都从原始内容开始）
        agent_a_working_strategies["value"] = original_strategies
        agent_a_result["tool_called"] = False

        # 执行 Agent
        await agent.run(memories, service_name)

        # 检查是否调用了工具
        if agent_a_result["tool_called"]:
            break  # 成功调用，退出重试

    # 检查是否最终失败
    if not agent_a_result["tool_called"]:
        raise RuntimeError(f"Agent A failed to call edit_strategies tool after {MAX_TOOL_CALL_RETRIES} attempts")
```

## 相关实现文档

- [可用的代码基础设施](./01_code_infrastructure.md)
- [文件夹结构设计](./02_folder_structure.md)
- [任务触发规范](./03_task_triggering.md)
- [错误处理规范](./04_error_handling.md)
- [日志记录规范](./05_logging.md)
- [Agent 实现示例](./07_agent_implementations/)
- [上下文文档](../background_update_task_spec_context.md)
- [设计文档](../background_update_task_spec_design.md)
