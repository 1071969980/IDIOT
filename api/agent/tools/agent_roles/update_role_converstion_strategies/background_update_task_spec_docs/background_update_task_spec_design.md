# 角色对话策略更新功能 - 设计文档

## 2.1 整体流程

后台更新任务分为三个主要阶段：

### 第一阶段：计划更新任务 (Planning Task)

**目的**: 防止多个任务同时处于第一阶段等待（后来者杀死先来者）

**执行逻辑**:
1. **任务启动前**：立即发布 `agent-role-update:planning:{user_id}:{role_name}` 信号
   - 这个信号会终止所有**正在第一阶段等待**的旧任务
   - 实现"后来者杀死先来者"的逻辑
2. **启动第一阶段**：订阅频道，开始等待 30 秒超时
3. 如果在等待期间收到新的 planning 信号，说明有更新的任务启动，当前任务退出
4. 如果等待超时（30 秒），说明没有更新的任务启动，继续执行第二阶段

**返回值语义**:
- `True`：超时（没有新任务来抢占），继续执行第二阶段
- `False`：收到新任务的信号，当前任务退出

**冲突谓词**: 相同用户的相同角色的计划更新任务

**分布式信号设计**:
- **频道命名规则**: `agent-role-update:planning:{user_id}:{role_name}`
- **信号发布时机**: **任务启动前**（在进入第一阶段之前）
- **信号订阅时机**: 第一阶段启动时，使用 `subscribe_to_event()` 订阅频道
- **信号作用**: 终止其他正在第一阶段等待的旧任务

**超时等待实现**:
- 使用 `asyncio.wait_for(event.wait(), timeout=30)` 实现
- 超时后抛出 `asyncio.TimeoutError`，捕获后返回 `True`（继续执行）
- 收到信号后 `event.wait()` 返回，返回 `False`（退出任务）

**关键设计要点**:
- 第一阶段只防止"多个任务同时进入第一阶段"，不检测第三阶段状态
- 第三阶段的并发控制由**分布式锁**保证（见第三阶段说明）
- 如果新任务在旧任务的第三阶段启动，新任务会在分布式锁处等待，不会进入第三阶段

### 第二阶段：准备文件内容 (Prepare File Contents)

**目的**: 读取所需的用户空间文件内容到内存，并处理缓存文件

**函数签名**: `async def execute_preparation_phase(user_id: UUID, role_name: str) -> tuple[str, str, str] | None`

**执行逻辑**:
1. 读取以下文件内容到内存变量：
   - `conversation_strategies.md` → `original_strategies: str`
   - `concluding_guidance.md` → `original_guidance: str`
   - `strategies_update_cache.json` → `update_cache: dict`
2. 读取后立即关闭文件句柄
3. **缓存文件特殊处理**:
   - 提取更新列表：`strategies_list = update_cache.get("strategies_update_cache", [])`
   - 如果 `strategies_list` 为空数组或不存在，则跳过第三阶段，任务正常结束（返回 `None`）
   - 将 `strategies_list` 格式化为易读文本（见下方格式化逻辑）
   - 只清空 `strategies_update_cache` 数组（保留其他 JSON 结构）：将 `update_cache["strategies_update_cache"]` 设置为空数组 `[]`
   - 将清空后的 `update_cache` 写回文件
   - 如果后续任务发生异常，将读取到的原始 `update_cache` 内容写回缓存文件
   - **并发安全性**: `HybridFileObject` 在 `async with` 块内持有分布式锁，不会发生请求丢失

**退出条件**:
- 如果 `strategies_list` 为空数组或不存在，返回 `None`，跳过第三阶段
- 如果读取文件时发生异常（文件不存在、权限错误等），记录错误日志，任务结束（返回 `None`）

**返回值**:
- 成功：返回 `(original_strategies, original_guidance, strategies_update_list)` 三个字符串的元组
  - `original_strategies`: 读取到的对话策略内容
  - `original_guidance`: 读取到的总结指导内容
  - `strategies_update_list`: 格式化后的更新请求文本
- 失败或无更新：返回 `None`

**strategies_list 格式化逻辑**:
```python
strategies_list = update_cache.get("strategies_update_cache", [])
if not strategies_list:
    return None  # 没有待处理的更新

# 格式化为易读文本
formatted_items = []
for i, item in enumerate(strategies_list, 1):
    formatted_items.append(
        f"## 更新请求 {i}\n\n"
        f"**更新内容**:\n{item['update_content']}\n\n"
        f"**相关上下文**:\n{item['context']}"
    )
strategies_update_list = "\n\n".join(formatted_items)
```

**异常处理**:
- 文件读取异常：使用 try-except 捕获，记录 logfire.error，任务结束（返回 `None`）
- 缓存文件清空异常：记录日志，但继续执行（因为已读取到内存）

### 第三阶段：更新任务 (Update Task)

**目的**: 执行实际的对话策略和总结指导文件更新

**函数签名**: `async def execute_update_phase(user_id: UUID, role_name: str, original_strategies: str, original_guidance: str, strategies_update_list: str) -> None`

**执行逻辑**:
1. **获取分布式锁**（阻塞等待，超时时间 300 秒）
   - 如果其他任务正在执行第三阶段，当前任务会在锁处等待
   - 锁释放后，当前任务开始执行
2. **启动 Agent 循环**，包括三个子任务：
   - 更新对话策略文件（Agent A）
   - 更新对话总结指导文件（Agent B）
   - 审查更新结果（Agent C）
3. 如果审查通过，将内存中的更新结果写入用户空间文件系统
4. 写入成功后，缓存文件已被第二阶段清空，无需额外处理
5. **释放分布式锁**
6. **无返回值**: 函数不返回任何值，成功或失败都通过日志记录

**分布式锁设计**:
- **锁命名规则**: `agent-role-update:lock:{user_id}:{role_name}`
- **锁超时时间**: 300 秒（5 分钟）
- **获取方式**: `async with RedisDistributedLock(key, timeout=300) as lock:`
- **作用**: 保证同一时间只有一个任务处于第三阶段（串行执行）

**关键设计要点**:
- **第三阶段不发布信号**：分布式锁已经保证了串行执行
- **新任务的处理**：如果在第三阶段执行期间有新任务到达，新任务会在分布式锁处等待
- **并发安全**：不会有两个任务同时修改用户空间文件

## 2.2 Agent 循环设计

### Agent A：更新对话策略文件

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
system_prompt = prompt.compile({
    "original_strategies": original_strategies,
    "strategies_update_cache": strategies_update_list,  # 格式化文本
    "review_suggestions": review_suggestions or ""
})
```

### Agent B：更新对话总结指导文件

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

**Langfuse 提示词路径**: `agent-role-update/update-guidance`

**提示词编译示例**:
```python
system_prompt = prompt.compile({
    "updated_strategies": updated_strategies,
    "original_guidance": original_guidance,
    "review_suggestions": review_suggestions or ""
})
```

### Agent C：审查更新结果

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
system_prompt = prompt.compile({
    "strategies_diff": strategies_diff,
    "guidance_diff": guidance_diff
})
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

## 2.3 循环重试次数说明

**工具调用重试（Agent A/B）**:
- 如果 Agent 未调用工具，立即重试
- 每个工具调用最多重试 3 次
- 超过 3 次后任务失败并回滚

**审查循环重试（Agent A → B → C 循环）**:
- 如果 Agent C 审查不通过（`score < 80`），重新执行 A → B → C
- 最多循环 3 次
- 超过 3 次后任务失败并回滚

**总执行次数上限**:
- 最坏情况下：Agent A 执行 9 次（3 次循环 × 3 次工具调用重试）
- Agent B 执行 9 次
- Agent C 执行 3 次

## 2.4 并发安全性保证

**分布式锁机制**:
- `HybridFileObject` 在 `async with` 块内自动获取分布式锁
- 锁的键名格式：`HybridFileObject:{s3_key}`
- 锁在退出 `async with` 块时自动释放

**并发读取安全性**:
- 第二阶段的文件读取操作不需要额外获取分布式锁
- 如果第三阶段正在执行（持有锁），第二阶段的读取会被阻塞
- 第三阶段完成并释放锁后，新的读取会获取最新内容
- 这种设计符合"读多写少"的场景，不需要额外的读写锁

**缓存文件并发安全**:
- 读取和清空 `strategies_update_cache.json` 在同一个 `async with` 块内执行
- `HybridFileObject` 持有分布式锁，确保原子性
- 不会发生请求丢失或竞态条件

## 2.5 文件操作设计

### 内存操作原则

**第二阶段（准备文件内容）**:
1. 一次性读取所需文件到内存：
   - `conversation_strategies.md` → `original_strategies: str`
   - `concluding_guidance.md` → `original_guidance: str`
   - `strategies_update_cache.json` → `update_cache: dict`
2. 读取后立即关闭文件句柄
3. 读取成功后，只清空 `strategies_update_cache` 数组（保留其他 JSON 结构）：
   - 提取 `strategies_list = update_cache.get("strategies_update_cache", [])`
   - 将 `update_cache["strategies_update_cache"]` 设置为 `[]`
   - 写回文件（保留其他可能的字段）
4. 如果 `strategies_list` 为空，跳过第三阶段，任务正常结束

**第三阶段（Agent 循环）**:
1. 使用内存数据构建动态工具，agent 看到的是普通的文件读写工具
2. Agent 输出结果保存到内存变量：
   - Agent A: `agent_a_result["updated_strategies"]`
   - Agent B: `agent_b_result["updated_guidance"]`
3. 审查通过后，才将内存数据写入文件系统：
   - `updated_strategies` → `conversation_strategies.md`
   - `updated_guidance` → `concluding_guidance.md`

### 缓存文件回滚机制

- 如果在第二阶段之后任何步骤失败，将读取到的 `update_cache` 写回 `strategies_update_cache.json`
- 使用 try-finally 确保回滚逻辑被执行

### 动态工具示例

**Agent A 的两个工具定义**:

```python
from pydantic import BaseModel, Field
from api.agent.tools.read_file.utils import read_from_string
from api.agent.tools.edit_file.utils import edit_string

# 工具1: read_strategies_part
class ReadStrategiesPartToolParam(BaseModel):
    """读取对话策略的部分内容"""
    offset: int = Field(default=0, ge=0, description="起始行号（从 0 开始）")
    limit: int = Field(default=100, ge=1, le=1000, description="读取的行数")

async def read_strategies_part_callback(
    param: ReadStrategiesPartToolParam,
    working_strategies: dict[str, str]
):
    """读取工作变量的部分内容"""
    return read_from_string(
        working_strategies["value"],
        offset=param.offset,
        limit=param.limit,
        add_line_numbers=True
    )

read_strategies_part_tool = construct_tool(
    "read_strategies_part",
    "读取对话策略文件的部分内容，帮助了解当前策略的具体内容。",
    ReadStrategiesPartToolParam,
    lambda param: read_strategies_part_callback(param, agent_a_working_strategies)
)

# 工具2: edit_strategies
class EditStrategiesToolParam(BaseModel):
    """编辑对话策略内容"""
    old_text: str = Field(..., description="要替换的原始文本")
    new_text: str = Field(..., description="替换后的新文本")
    replace_all: bool = Field(default=False, description="是否替换所有出现")

async def edit_strategies_callback(
    param: EditStrategiesToolParam,
    working_strategies: dict[str, str],
    result_container: AgentAResult
):
    """编辑工作变量"""
    working_strategies["value"] = edit_string(
        string=working_strategies["value"],
        old_text=param.old_text,
        new_text=param.new_text,
        replace_all=param.replace_all
    )
    result_container["tool_called"] = True  # 标记已调用

edit_strategies_tool = construct_tool(
    "edit_strategies",
    "编辑对话策略的内容。使用 old_text 和 new_text 参数进行文本替换。",
    EditStrategiesToolParam,
    lambda param: edit_strategies_callback(param, agent_a_working_strategies, agent_a_result)
)
```

**关键设计要点**:
1. **工作容器**（`agent_a_working_strategies`）使用可变 `dict`，允许工具闭包修改
2. **结果容器**（`agent_a_result`）使用 TypedDict，存储执行状态
3. **read 工具**直接返回读取的内容（通过 Agent 响应返回给 LLM）
4. **edit 工具**修改工作容器并设置 `tool_called` 标记
5. **重试逻辑**检查 `agent_a_result["tool_called"]` 判断是否成功

## 流程图

```
┌─────────────────────────────────────────────────────────────────┐
│                        工具调用成功                              │
│                  写入缓存文件成功                                 │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│               0. 任务启动前：发布 planning 信号                   │
│  1. 发布信号到: agent-role-update:planning:{user_id}:{role}    │
│  2. 信号作用：终止所有正在第一阶段等待的旧任务（后来者杀死先来者）│
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   第一阶段：计划更新任务                          │
│  1. 订阅分布式信号: agent-role-update:planning:{user_id}:{role} │
│  2. 等待 30 秒超时（使用 asyncio.wait_for）                      │
│  3. 如果收到信号 → 有新任务来抢占，当前任务退出                   │
│  4. 如果超时 → 没有新任务，进入第二阶段                          │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                 第二阶段：准备文件内容                            │
│  1. 读取 conversation_strategies.md → original_strategies       │
│  2. 读取 concluding_guidance.md → original_guidance             │
│  3. 读取 strategies_update_cache.json → update_cache            │
│  4. 只清空 strategies_update_cache 数组（设为 []）               │
│  5. 如果 strategies_list 为空 → 任务结束                          │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   第三阶段：更新任务（Agent 循环）                │
│  1. 获取分布式锁: agent-role-update:lock:{user_id}:{role}       │
│     (如果其他任务正在执行，在锁处等待)                            │
│  2. 启动 Agent 循环：                                           │
│     - Agent A: 更新对话策略（工具调用最多重试 3 次）               │
│     - Agent B: 更新总结指导（工具调用最多重试 3 次）               │
│     - Agent C: 审查更新结果（生成 diff，评分 0-100）               │
│  3. 如果 score < 80 → 回到 Agent A（最多循环 3 次）              │
│  4. 如果 score >= 80 → 写入文件系统                              │
│  5. 释放分布式锁                                                │
└─────────────────────────────────────────────────────────────────┘
```

## 相关设计文档

- [上下文文档](./background_update_task_spec_context.md)
- [实现文档](./background_update_task_spec_implementation.md)
- [审核文档](./background_update_task_spec_review.md)
