---
文档标题：Agent 循环设计
文档描述：描述三个 Agent（A、B、C）的详细设计，包括 Agent A 更新对话策略文件、Agent B 更新总结指导文件、Agent C 审查更新结果的输入注入、动态工具、执行控制、输出存储和提示词路径。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [2.2.1 Agent A：更新对话策略文件](#221-agent-a更新对话策略文件)
- [2.2.2 Agent B：更新对话总结指导文件](#222-agent-b更新对话总结指导文件)
- [2.2.3 Agent C：审查更新结果](#223-agent-c审查更新结果)

## 2.2 Agent 循环设计

### 2.2.1 Agent A：更新对话策略文件

**函数签名**:
```python
async def run_agent_a_update_strategies(
    original_strategies: str,
    strategies_update_list: str,
    review_suggestions: str | None,
    service_name: str,
    agent_a_working_strategies: dict[str, str],
    agent_a_result: AgentAResult
) -> None
```

**输入注入**:
- `original_strategies`: 当前的对话策略（从 `conversation_strategies.md` 读取到内存）
- `strategies_update_list`: 格式化后的更新请求文本（从 `strategies_update_cache.json` 提取并格式化）
- `review_suggestions`: 审查建议（第一轮执行时为 `None`，后续循环时传入 Agent C 的 `suggestions`）
- `agent_a_working_strategies`: 工作容器（可变 dict，初始值为 `{"value": original_strategies}`，由工具闭包捕获并修改）
- `agent_a_result`: 结果容器（TypedDict，存储执行状态和最终结果）

**动态工具**:
1. **read_strategies_part**: 读取工作变量的部分内容（使用 `read_from_string`）
   - 参数：`offset: int`（起始行号），`limit: int`（读取行数）
   - 返回：指定范围的文本内容（带行号）

2. **edit_strategies**: 编辑工作变量（使用 `edit_string`）
   - 参数：`old_text: str`（要替换的文本），`new_text: str`（新文本），`replace_all: bool`（是否替换所有出现）
   - 功能：直接修改 `agent_a_working_strategies["value"]`
   - 副作用：设置 `agent_a_result["tool_called"] = True`

**执行控制**:
- 使用 `AgentBase` 作为基类
- 提示词通过 Langfuse 获取，使用 `prompt.compile()` 方法编译提示词模板
- **重试逻辑**: 如果 `edit_strategies` 工具未被调用，重置工作容器并重新运行 Agent，最多重试 3 次
- **无返回值**: 函数不返回任何值，通过修改外部容器传递结果

**输出存储**:
- 工作变量由 `edit_strategies` 工具闭包直接修改
- Agent 执行完毕后，`execute_update_phase` 从 `agent_a_working_strategies["value"]` 提取最终结果

**Langfuse 提示词路径**: `agent-role-update/update-strategies`

**提示词编译示例**:
```python
system_prompt = prompt.compile(
    original_strategies=original_strategies,
    strategies_update_cache=strategies_update_list,  # 格式化文本
    review_suggestions=review_suggestions or ""
)
```

### 2.2.2 Agent B：更新对话总结指导文件

**函数签名**:
```python
async def run_agent_b_update_guidance(
    updated_strategies: str,
    original_guidance: str,
    review_suggestions: str | None,
    service_name: str,
    agent_b_working_guidance: dict[str, str],
    agent_b_result: AgentBResult
) -> None
```

**输入注入**:
- `updated_strategies`: 更新过的对话策略（来自外部容器 `agent_a_result["updated_strategies"]`）
- `original_guidance`: 当前的对话总结指导（从 `concluding_guidance.md` 读取到内存）
- `review_suggestions`: 审查建议（第一轮执行时为 `None`，后续循环时传入 Agent C 的 `suggestions`）
- `agent_b_working_guidance`: 工作容器（可变 dict，初始值为 `{"value": original_guidance}`，由工具闭包捕获并修改）
- `agent_b_result`: 结果容器（TypedDict，存储执行状态和最终结果）

**动态工具**:
1. **read_guidance_part**: 读取工作变量的部分内容（使用 `read_from_string`）
   - 参数：`offset: int`（起始行号），`limit: int`（读取行数）
   - 返回：指定范围的文本内容（带行号）

2. **edit_guidance**: 编辑工作变量（使用 `edit_string`）
   - 参数：`old_text: str`（要替换的文本），`new_text: str`（新文本），`replace_all: bool`（是否替换所有出现）
   - 功能：直接修改 `agent_b_working_guidance["value"]`
   - 副作用：设置 `agent_b_result["tool_called"] = True`

**执行控制**:
- 使用 `AgentBase` 作为基类
- 提示词通过 Langfuse 获取，使用 `prompt.compile()` 方法编译提示词模板
- **重试逻辑**: 如果 `edit_guidance` 工具未被调用，重置工作容器并重新运行 Agent，最多重试 3 次
- **无返回值**: 函数不返回任何值，通过修改外部容器传递结果

**输出存储**:
- 工作变量由 `edit_guidance` 工具闭包直接修改
- Agent 执行完毕后，`execute_update_phase` 从 `agent_b_working_guidance["value"]` 提取最终结果

**Langfuse 提示词路径**: `agent-role-update/update-conclusion-guidance`

**提示词编译示例**:
```python
system_prompt = prompt.compile(
    updated_strategies=updated_strategies,
    original_guidance=original_guidance,
    review_suggestions=review_suggestions or ""
)
```

### 2.2.3 Agent C：审查更新结果

**函数签名**:
```python
async def run_agent_c_review(
    original_strategies: str,
    original_guidance: str,
    updated_strategies: str,
    updated_guidance: str,
    service_name: str,
    agent_c_result: AgentCResult
) -> None
```

**输入注入**:
- `original_strategies`: 原始的对话策略（从 `conversation_strategies.md` 读取到内存）
- `original_guidance`: 原始的对话总结指导（从 `concluding_guidance.md` 读取到内存）
- `updated_strategies`: 更新过的对话策略（来自外部容器 `agent_a_result["updated_strategies"]`）
- `updated_guidance`: 更新过的对话总结指导（来自外部容器 `agent_b_result["updated_guidance"]`）
- `agent_c_result`: 结果容器（TypedDict，存储审查分数和建议）
- Agent C 在内部生成 diff（使用 Python `difflib.unified_diff`）
- 审查标准（通过 Langfuse 提示词模板注入）

**动态工具**:
1. **submit_review_result**: 提交审查结果
   - 参数：`score: int`（审查分数，0-100），`suggestions: str`（修改建议）
   - 功能：写入 `agent_c_result["score"]` 和 `agent_c_result["suggestions"]`

**执行控制**:
- 使用 `AgentBase` 作为基类
- 提示词通过 Langfuse 获取，使用 `prompt.compile()` 方法编译提示词模板
- **无返回值**: 函数不返回任何值，通过修改外部容器传递结果

**输出存储**:
- 工具回调函数将审查结果写入 `agent_c_result["score"]` 和 `agent_c_result["suggestions"]`

**审查通过标准**:
- 代码根据外部容器 `agent_c_result["score"] >= 80` 判断是否通过
- 如果 `score >= 80`，审查通过，退出循环
- 如果 `score < 80`，审查不通过，回到 Agent A 重新执行

**循环逻辑**:
- 设置最大审查循环次数为 3 次
- 如果不通过（`score < 80`），回到 Agent A，注入 `agent_c_result["suggestions"]` 重新执行
- 超过最大循环次数后，任务终止并记录错误

**Langfuse 提示词路径**: `agent-role-update/review-updates`

**提示词编译示例**:
```python
system_prompt = prompt.compile(
    strategies_diff=strategies_diff,
    guidance_diff=guidance_diff
)
```

**Diff 格式说明**:
- 使用 Python 标准库 `difflib.unified_diff` 生成 unified diff 格式
- diff 格式示例：
  ```diff
  --- Original
  +++ Updated
  @@ -5,7 +5,7 @@
   -旧内容
   +新内容
  ```
- 将 diff 文本嵌入提示词模板中，作为 Agent C 的输入

## 相关文档

- [整体流程设计](./01_overall_flow.md)
- [上下文文档](../background_update_task_spec_context.md)
- [实现文档](../background_update_task_spec_implementation.md)
