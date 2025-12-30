# 角色对话策略更新功能 - 文件夹结构设计

---
文档标题：background_update_task_spec_implementation
文档描述：本文档描述角色对话策略更新功能的文件夹结构设计，包括整体目录结构、文件职责说明、模块依赖关系图和设计原则。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [文件夹结构设计](#文件夹结构设计)
    - [整体目录结构](#整体目录结构)
    - [文件职责说明](#文件职责说明)
    - [模块依赖关系图](#模块依赖关系图)
    - [设计原则](#设计原则)

## 文件夹结构设计

### 整体目录结构

```
../../../../api/agent/tools/agent_roles/update_role_conversation_strategies/
├── __init__.py                                              # 现有文件
├── constructor.py                                            # 现有文件，需要修改
├── config_data_model.py                                      # 现有文件
├── background_update/                                        # 新增目录
│   ├── __init__.py                                           # 包初始化
│   ├── task_runner.py                                        # 后台任务主入口
│   ├── phase1_planning.py                                    # 第一阶段：计划任务
│   ├── phase2_preparation.py                                 # 第二阶段：准备文件内容
│   ├── phase3_update.py                                      # 第三阶段：更新任务
│   ├── agents/                                               # Agent 实现子模块
│   │   ├── __init__.py
│   │   ├── agent_a_update_strategies.py                      # Agent A：更新对话策略
│   │   ├── agent_b_update_guidance.py                        # Agent B：更新总结指导
│   │   └── agent_c_review.py                                 # Agent C：审查更新结果
│   └── models.py                                             # 数据模型和工具定义
└── background_update_task_spec_docs/                         # 规范文档目录
    ├── background_update_task_spec_context.md
    ├── background_update_task_spec_design.md
    ├── background_update_task_spec_implementation.md
    └── background_update_task_spec_review.md
```

### 文件职责说明

#### `constructor.py` (现有文件，需修改)
- **职责**: 工具的构造函数，处理用户调用
- **修改内容**:
  - 在 `__call__` 方法中，写入缓存成功后，立即发起后台更新任务
  - 使用 `asyncio.create_task()` 创建后台任务，调用 `task_runner.run_background_update_task()`
- **关键代码**:
  ```python
  # 写入缓存成功后，立即发起后台更新任务
  task = asyncio.create_task(
      run_background_update_task(
          user_id=self.user_id,
          role_name=param.role_name
      )
  )
  ```

#### `background_update/__init__.py`
- **职责**: 包初始化，导出公共接口
- **导出内容**:
  - `run_background_update_task` - 主入口函数
  - 各阶段的执行函数（可选，如果需要外部测试）

#### `background_update/task_runner.py`
- **职责**: 后台更新任务的主入口和流程协调
- **主要功能**:
  - `async def run_background_update_task(user_id, role_name)` - 主入口函数
  - **0. 任务启动前：发布 planning 信号**（终止其他等待的任务）
  - 调用三个阶段的执行函数
  - 设置 Langfuse 日志上下文
  - 顶层异常捕获和日志记录
- **依赖**:
  - `phase1_planning.py` - 第一阶段
  - `phase2_preparation.py` - 第二阶段
  - `phase3_update.py` - 第三阶段
  - `../../../../api/redis/pubsub.py` - Redis 发布订阅

#### `background_update/phase1_planning.py`
- **职责**: 第一阶段 - 计划更新任务（防止多个任务同时进入第一阶段）
- **主要功能**:
  - `async def execute_planning_phase(user_id, role_name, timeout=30)` - 执行计划阶段
  - **关键实现**: `subscribe_to_event()` 会阻塞直到收到消息，必须作为后台任务运行
  - 订阅 Redis 频道 `agent-role-update:planning:{user_id}:{role_name}`
  - 使用 `asyncio.create_task()` 创建订阅任务，然后使用 `asyncio.wait_for(event.wait(), timeout=30)` 等待
  - 等待分布式信号（超时 30 秒）
  - 无论超时还是收到信号，都取消订阅任务并清理
  - 返回是否应该继续执行（`True` 表示超时继续，`False` 表示收到信号退出）
- **依赖**:
  - `../../../../api/redis/pubsub.py` - Redis 发布订阅

#### `background_update/phase2_preparation.py`
- **职责**: 第二阶段 - 准备文件内容
- **主要功能**:
  - `async def execute_preparation_phase(user_id: UUID, role_name: str) -> tuple[str, str, str] | None` - 执行准备阶段
  - **缓存文件操作**（在同一个分布式锁内完成，确保原子性）：
    - 使用 `r+` 模式打开 `strategies_update_cache.json`
    - 在同一个 `async with` 块内完成：
      - 读取并解析缓存文件内容
      - 提取 `strategies_list = update_cache.get("strategies_update_cache", [])`
      - 如果为空，返回 `None`（跳过第三阶段）
      - 将 `strategies_list` 格式化为易读文本（在锁内完成，操作很快）
      - 清空 `strategies_update_cache` 数组
      - 使用 `seek(0)`、`write()`、`truncate()` 写回文件
      - 释放分布式锁
  - **其他文件读取**（独立操作）：
    - `conversation_strategies.md` → `original_strategies: str`
    - `concluding_guidance.md` → `original_guidance: str`
  - 返回三个字符串的元组：`(original_strategies, original_guidance, strategies_update_list)`
  - 处理异常（文件不存在、读取失败等），不向上抛出，返回 `None`
- **并发安全**: 所有缓存文件操作在同一个分布式锁内完成，避免竞态条件
- **依赖**:
  - `../../../../api/agent/tools/agent_roles/utils.py` - 文件系统工具函数
  - `../../../../api/user_space/file_system/fs_utils/exception.py` - 异常类型

#### `background_update/phase3_update.py`
- **职责**: 第三阶段 - 更新任务（Agent 循环）
- **主要功能**:
  - `async def execute_update_phase(user_id: UUID, role_name: str, original_strategies: str, original_guidance: str, strategies_update_list: str) -> None` - 执行更新阶段
  - 获取分布式锁 `agent-role-update:lock:{user_id}:{role_name}`，**超时时间设置为 300 秒**
  - **不发布信号**：分布式锁已经保证了串行执行
  - 执行 Agent A、B、C 循环（最多循环 3 次）
  - 检查外部容器 `agent_c_result["score"]`，如果 `score >= 80` 则通过
  - 审查通过后写入文件系统
  - 处理异常和回滚
  - **无返回值**: 函数不返回任何值，成功或失败都通过日志记录
- **依赖**:
  - `../../../../api/redis/distributed_lock.py` - Redis 分布式锁
  - `agents/` 子模块 - Agent 实现
  - `models.py` - 常量定义（如 `PHASE3_LOCK_TIMEOUT`）

#### `background_update/agents/__init__.py`
- **职责**: Agent 子模块初始化，导出 Agent 执行函数
- **导出内容**:
  - `run_agent_a_update_strategies` - Agent A 执行函数
  - `run_agent_b_update_guidance` - Agent B 执行函数
  - `run_agent_c_review` - Agent C 执行函数

#### `background_update/agents/agent_a_update_strategies.py`
- **职责**: Agent A - 更新对话策略文件
- **主要功能**:
  - `async def run_agent_a_update_strategies(original_strategies: str, strategies_update_list: str, review_suggestions: str | None, service_name: str, agent_a_working_strategies: dict[str, str], agent_a_result: AgentAResult) -> None`
  - 从 Langfuse 获取提示词模板 `"agent-role-update/update-strategies"`（**注意**：`_get_prompt_from_langfuse` 是同步函数，不需要 `await`）
  - 使用 `prompt.compile()` 编译提示词，传入业务参数
  - 构造两个动态工具：`read_strategies_part` 和 `edit_strategies`
  - 构造 OpenAI 格式的记忆（memories）
  - 使用 `AgentBase.run()` 执行
  - 重试逻辑：如果 `edit_strategies` 工具未被调用，重置工作容器并重试最多 3 次
  - **无返回值**: 函数不返回任何值，通过修改外部容器传递结果
- **依赖**:
  - `../../../../api/agent/base_agent.py` - AgentBase 类
  - `../../../../docs/for_LLM_dev/dynamic_tool_DI/` - 动态工具 DI
  - `../../../../api/workflow/langfuse_prompt_template/` - Langfuse 提示词
  - `../../../../api/agent/tools/read_file/utils.py` - read_from_string 函数
  - `../../../../api/agent/tools/edit_file/utils.py` - edit_string 函数
  - `models.py` - 数据模型和常量

#### `background_update/agents/agent_b_update_guidance.py`
- **职责**: Agent B - 更新对话总结指导文件
- **主要功能**:
  - `async def run_agent_b_update_guidance(updated_strategies: str, original_guidance: str, review_suggestions: str | None, service_name: str, agent_b_working_guidance: dict[str, str], agent_b_result: AgentBResult) -> None`
  - 从 Langfuse 获取提示词模板 `"agent-role-update/update-conclusion-guidance"`（**注意**：`_get_prompt_from_langfuse` 是同步函数，不需要 `await`）
  - 使用 `prompt.compile()` 编译提示词，传入业务参数
  - 构造两个动态工具：`read_guidance_part` 和 `edit_guidance`
  - 构造 OpenAI 格式的记忆（memories）
  - 使用 `AgentBase.run()` 执行
  - 重试逻辑：如果 `edit_guidance` 工具未被调用，重置工作容器并重试最多 3 次
  - **无返回值**: 函数不返回任何值，通过修改外部容器传递结果
- **依赖**: 同 Agent A

#### `background_update/agents/agent_c_review.py`
- **职责**: Agent C - 审查更新结果
- **主要功能**:
  - `async def run_agent_c_review(original_strategies: str, original_guidance: str, updated_strategies: str, updated_guidance: str, service_name: str, agent_c_result: AgentCResult) -> None`
  - 生成 diff（使用 `difflib.unified_diff`）
  - 从 Langfuse 获取提示词模板 `"agent-role-update/review-updates"`（**注意**：`_get_prompt_from_langfuse` 是同步函数，不需要 `await`）
  - 使用 `prompt.compile()` 编译提示词，传入 diff 文本
  - 构造动态工具：`submit_review_result`
  - 构造 OpenAI 格式的记忆（memories）
  - 使用 `AgentBase.run()` 执行
  - **无返回值**: 函数不返回任何值，审查结果通过工具闭包写入外部容器
- **Diff 生成**:
  ```python
  import difflib

  def generate_diff(original: str, updated: str, filename: str = "file") -> str:
      """生成 unified diff 格式"""
      original_lines = original.splitlines(keepends=True)
      updated_lines = updated.splitlines(keepends=True)
      diff = difflib.unified_diff(
          original_lines,
          updated_lines,
          fromfile=f"Original {filename}",
          tofile=f"Updated {filename}",
          lineterm=""
      )
      return "".join(diff)
  ```
- **依赖**: 同 Agent A，额外依赖 Python 标准库 `difflib`

#### `background_update/models.py`
- **职责**: 数据模型和工具参数定义
- **主要功能**:
  - 定义 Agent 工具的参数模型（Pydantic BaseModel）
  - 定义外部容器的类型（TypedDict，用于闭包捕获变量）
  - 定义常量（如最大循环次数、超时时间、审查分数阈值等）
- **重要说明**:
  - 以下 TypedDict 定义了外部容器的类型，这些容器由 Dynamic Tool DI 的工具闭包捕获
  - Agent 函数本身**不返回任何值**（返回类型为 `None`）
  - Agent 执行结果通过工具回调函数（闭包）写入这些外部容器
  - 调用 Agent 前，需要先声明这些容器变量；调用后，从容器中读取结果
- **数据模型定义**:
  ```python
  from pydantic import BaseModel, Field
  from typing import TypedDict

  # ========== 工具参数模型 ==========

  class UpdateStrategiesToolParam(BaseModel):
      """Agent A 的工具参数：更新对话策略"""
      content: str = Field(..., description="更新后的对话策略内容")

  class UpdateGuidanceToolParam(BaseModel):
      """Agent B 的工具参数：更新总结指导"""
      content: str = Field(..., description="更新后的总结指导内容")

  class SubmitReviewToolParam(BaseModel):
      """Agent C 的工具参数：提交审查结果"""
      score: int = Field(..., ge=0, le=100, description="审查分数（0-100）")
      suggestions: str = Field(default="", description="修改建议")

  # ========== 外部容器类型定义（闭包捕获变量） ==========

  class AgentAResult(TypedDict):
      """Agent A 的外部容器类型（由工具闭包捕获并修改）"""
      updated_strategies: str  # 工具回调函数写入更新后的策略
      tool_called: bool  # 工具回调函数标记是否调用了工具

  class AgentBResult(TypedDict):
      """Agent B 的外部容器类型（由工具闭包捕获并修改）"""
      updated_guidance: str  # 工具回调函数写入更新后的指导
      tool_called: bool  # 工具回调函数标记是否调用了工具

  class AgentCResult(TypedDict):
      """Agent C 的外部容器类型（由工具闭包捕获并修改）"""
      score: int  # 工具回调函数写入审查分数
      suggestions: str  # 工具回调函数写入修改建议

  # ========== 常量定义 ==========

  # 工具调用最大重试次数
  MAX_TOOL_CALL_RETRIES = 3

  # 审查循环最大次数
  MAX_REVIEW_LOOPS = 3

  # 审查通过分数阈值
  REVIEW_PASS_THRESHOLD = 80

  # 第一阶段超时时间（秒）
  PHASE1_TIMEOUT = 30

  # 第三阶段分布式锁超时时间（秒）
  PHASE3_LOCK_TIMEOUT = 300
  ```

### 模块依赖关系图

```
constructor.py
    ↓
background_update/task_runner.py
    ↓
    ├─→ phase1_planning.py
    │       └─→ api/redis/pubsub.py
    │
    ├─→ phase2_preparation.py
    │       ├─→ api/agent/tools/agent_roles/utils.py
    │       └─→ api/user_space/file_system/fs_utils/exception.py
    │
    └─→ phase3_update.py
            ├─→ api/redis/distributed_lock.py
            ├─→ api/redis/pubsub.py
            └─→ agents/
                    ├─→ agent_a_update_strategies.py
                    ├─→ agent_b_update_guidance.py
                    └─→ agent_c_review.py
                            ├─→ api/agent/base_agent.py
                            ├─→ docs/for_LLM_dev/dynamic_tool_DI/
                            └─→ api/workflow/langfuse_prompt_template/
```

### 设计原则

1. **模块化**: 每个阶段独立成一个模块，职责单一
2. **可测试性**: 每个模块可以独立测试
3. **可维护性**: 代码结构清晰，易于定位和修改
4. **可扩展性**: 如果需要添加新的阶段或 Agent，只需添加新文件
5. **错误隔离**: 每个阶段的异常不向上传播，通过日志记录

## 相关实现文档

- [可用的代码基础设施](./01_code_infrastructure.md)
- [任务触发规范](./03_task_triggering.md)
- [错误处理规范](./04_error_handling.md)
- [日志记录规范](./05_logging.md)
- [外部容器管理策略](./06_container_management.md)
- [Agent 实现示例](./07_agent_implementations/)
- [上下文文档](../background_update_task_spec_context.md)
- [设计文档](../background_update_task_spec_design.md)
