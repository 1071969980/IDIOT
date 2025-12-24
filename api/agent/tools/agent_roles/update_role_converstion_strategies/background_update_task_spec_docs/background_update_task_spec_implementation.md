# 角色对话策略更新功能 - 实现文档

## 3.1 可用的代码基础设施

### AgentBase (`<project_work_dir>/api/agent/base_agent.py`)

**核心方法**: `async def run(memories, service_name, thinking=True)`

**参数**:
- `memories`: 对话历史（`list[ChatCompletionMessageParam]`）
- `service_name`: 使用的 LLM 服务名称
- `thinking`: 是否启用思考模式（默认 `True`）

**返回**: `(new_memories, new_messages)` 元组

**循环控制**: 通过 `loop_control` 参数和生命周期方法控制循环行为

### 动态工具 DI (`<project_work_dir>/docs/for_LLM_dev/dynamic_tool_DI的设计和使用.md`)

**核心函数**: `construct_tool(tool_name, tool_description, tool_param_model, call_back)`

**输入**:
- `tool_name`: str - AI 调用时使用的工具名
- `tool_description`: str - 告诉 AI 这个工具干什么
- `tool_param_model`: type[BaseModel] - Pydantic 模型，定义参数结构
- `call_back`: Callable - 业务逻辑函数（async）

**输出**: `(tool_define, tool_closure)` 元组
- `tool_define`: `ChatCompletionToolParam` - 给 AI 看的工具定义
- `tool_closure`: `ToolClosure` - 程序实际执行的闭包

### Langfuse 提示词模板 (`<project_work_dir>/api/workflow/langfuse_prompt_template`)

**核心函数**: `_get_prompt_from_langfuse(prompt_path, production=True, label=None, version=None)`

**返回**: `TextPromptClient` 或 `None`

**提示词路径格式**:
- 使用斜杠分隔的命名空间格式（类似文件路径）
- 示例：`"agent-role-update/update-strategies"`
- 格式：`"<feature-name>/<prompt-name>"`

**提示词编译（compile）**:
- `TextPromptClient` 对象有 `compile()` 方法
- 接受字典参数，key 是模板中的变量名，value 是变量的值
- 返回编译后的提示词字符串

**使用方式**:
```python
from api.workflow.langfuse_prompt_template.constant import _get_prompt_from_langfuse

# 1. 获取提示词模板
prompt = await _get_prompt_from_langfuse("agent-role-update/update-strategies")
if not prompt:
    raise ValueError("Prompt not found in Langfuse")

# 2. 编译提示词（传入业务参数）
system_prompt = prompt.compile({
    "original_strategies": original_strategies,
    "strategies_update_cache": strategies_update_list,
    "review_suggestions": review_suggestions or ""
})

# 3. 构造 OpenAI 格式的记忆
memories = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": "请根据上下文更新对话策略"}
]
```

**已配置的提示词路径**:
- Agent A: `"agent-role-update/update-strategies"`
- Agent B: `"agent-role-update/update-guidance"`
- Agent C: `"agent-role-update/review-updates"`

### Redis 分布式锁 (`<project_work_dir>/api/redis/distributed_lock.py`)

**类**: `RedisDistributedLock`

**使用方式**: `async with RedisDistributedLock(key, timeout=30) as lock:`

### Redis 发布订阅 (`<project_work_dir>/api/redis/pubsub.py`)

**发布**: `await publish_event(channel)`

**订阅**: `event = asyncio.Event(); await subscribe_to_event(channel, event)`

## 3.2 文件夹结构设计

### 整体目录结构

```
<project_work_dir>/api/agent/tools/agent_roles/update_role_converstion_strategies/
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
  - `<project_work_dir>/api/redis/pubsub.py` - Redis 发布订阅

#### `background_update/phase1_planning.py`
- **职责**: 第一阶段 - 计划更新任务（防止多个任务同时进入第一阶段）
- **主要功能**:
  - `async def execute_planning_phase(user_id, role_name, timeout=30)` - 执行计划阶段
  - 订阅 Redis 频道 `agent-role-update:planning:{user_id}:{role_name}`
  - 等待分布式信号（超时 30 秒）
  - 返回是否应该继续执行（`True` 表示超时继续，`False` 表示收到信号退出）
- **依赖**:
  - `<project_work_dir>/api/redis/pubsub.py` - Redis 发布订阅

#### `background_update/phase2_preparation.py`
- **职责**: 第二阶段 - 准备文件内容
- **主要功能**:
  - `async def execute_preparation_phase(user_id: UUID, role_name: str) -> tuple[str, str, str] | None` - 执行准备阶段
  - 读取三个文件到内存：
    - `conversation_strategies.md` → `original_strategies: str`
    - `concluding_guidance.md` → `original_guidance: str`
    - `strategies_update_cache.json` → `update_cache: dict`
  - 提取 `strategies_list = update_cache.get("strategies_update_cache", [])`
  - 如果 `strategies_list` 为空，返回 `None`（跳过第三阶段）
  - 将 `strategies_list` 格式化为易读文本 `strategies_update_list`
  - 清空缓存文件的 `strategies_update_cache` 数组（保留其他 JSON 结构）
  - 返回三个字符串的元组：`(original_strategies, original_guidance, strategies_update_list)`
  - 处理异常（文件不存在、读取失败等），不向上抛出，返回 `None`
- **依赖**:
  - `<project_work_dir>/api/agent/tools/agent_roles/utils.py` - 文件系统工具函数
  - `<project_work_dir>/api/user_space/file_system/fs_utils/exception.py` - 异常类型

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
  - `<project_work_dir>/api/redis/distributed_lock.py` - Redis 分布式锁
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
  - 从 Langfuse 获取提示词模板 `"agent-role-update/update-strategies"`
  - 使用 `prompt.compile()` 编译提示词，传入业务参数
  - 构造两个动态工具：`read_strategies_part` 和 `edit_strategies`
  - 构造 OpenAI 格式的记忆（memories）
  - 使用 `AgentBase.run()` 执行
  - 重试逻辑：如果 `edit_strategies` 工具未被调用，重置工作容器并重试最多 3 次
  - **无返回值**: 函数不返回任何值，通过修改外部容器传递结果
- **依赖**:
  - `<project_work_dir>/api/agent/base_agent.py` - AgentBase 类
  - `<project_work_dir>/docs/for_LLM_dev/dynamic_tool_DI的设计和使用.md` - 动态工具 DI
  - `<project_work_dir>/api/workflow/langfuse_prompt_template/constant.py` - Langfuse 提示词
  - `<project_work_dir>/api/agent/tools/read_file/utils.py` - read_from_string 函数
  - `<project_work_dir>/api/agent/tools/edit_file/utils.py` - edit_string 函数
  - `models.py` - 数据模型和常量

#### `background_update/agents/agent_b_update_guidance.py`
- **职责**: Agent B - 更新对话总结指导文件
- **主要功能**:
  - `async def run_agent_b_update_guidance(updated_strategies: str, original_guidance: str, review_suggestions: str | None, service_name: str, agent_b_working_guidance: dict[str, str], agent_b_result: AgentBResult) -> None`
  - 从 Langfuse 获取提示词模板 `"agent-role-update/update-guidance"`
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
  - 从 Langfuse 获取提示词模板 `"agent-role-update/review-updates"`
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

## 3.3 任务触发规范

### 在 `constructor.py` 中的集成

```python
async def __call__(self, **kwargs):
    # 1. 参数验证
    param = UpdateConversationStrategiesOfRoleParam(**kwargs)

    # 2. 读取现有缓存
    async with user_agent_role_strategies_update_cache_file(self.user_id, param.role_name, "r") as f:
        cache_content = f.read().decode("utf-8")
        update_cache = ujson.loads(cache_content) if cache_content else {}

    # 3. 添加新更新请求到缓存
    if "strategies_update_cache" not in update_cache:
        update_cache["strategies_update_cache"] = []
    update_cache["strategies_update_cache"].append({
        "update_content": param.update_content,
        "context": param.context
    })

    # 4. 写入缓存文件
    async with user_agent_role_strategies_update_cache_file(self.user_id, param.role_name, "w") as f:
        f.write(ujson.dumps(update_cache).encode("utf-8"))

    # 5. 【关键位置】写入缓存成功后，立即发起后台更新任务
    from api.agent.tools.agent_roles.update_role_converstion_strategies.background_update.task_runner import run_background_update_task

    task = asyncio.create_task(
        run_background_update_task(
            user_id=self.user_id,
            role_name=param.role_name
        )
    )

    # 6. 返回成功消息（不等待任务完成）
    return ToolTaskResult(
        str_content="更新任务已提交，后台将自动处理。"
    )
```

**注意事项**:
- 使用 `asyncio.create_task()` 创建后台任务，不使用 `await` 等待
- 任务立即返回，不阻塞用户交互
- 后台任务的异常不会影响主流程（后台任务会自己记录日志）

### 在 `task_runner.py` 中的完整实现

```python
from uuid import UUID
import asyncio
import logfire
from api.redis.pubsub import publish_event

async def run_background_update_task(user_id: UUID, role_name: str) -> None:
    """
    后台更新任务的主入口函数

    执行流程:
    0. 任务启动前：发布 planning 信号（终止其他等待的任务）
    1. 第一阶段：计划更新任务（等待 30 秒）
    2. 第二阶段：准备文件内容
    3. 第三阶段：更新任务（Agent 循环）
    """
    channel = f"agent-role-update:planning:{user_id}:{role_name}"

    # ========== 0. 任务启动前：发布 planning 信号 ==========
    # 这个信号会终止所有正在第一阶段等待的旧任务
    # 实现"后来者杀死先来者"的逻辑
    await publish_event(channel)
    logfire.info("agent-role-update::task_started", user_id=str(user_id), role_name=role_name)

    try:
        # ========== 1. 第一阶段：计划更新任务 ==========
        continue_task = await execute_planning_phase(user_id, role_name)
        if not continue_task:
            logfire.info("agent-role-update::exited_by_newer_task")
            return  # 有更新的任务启动，当前任务退出

        # ========== 2. 第二阶段：准备文件内容 ==========
        preparation_result = await execute_preparation_phase(user_id, role_name)
        if preparation_result is None:
            logfire.info("agent-role-update::no_updates_pending")
            return  # 没有待处理的更新

        original_strategies, original_guidance, strategies_update_list = preparation_result

        # ========== 3. 第三阶段：更新任务 ==========
        await execute_update_phase(
            user_id=user_id,
            role_name=role_name,
            original_strategies=original_strategies,
            original_guidance=original_guidance,
            strategies_update_list=strategies_update_list
        )

        logfire.info("agent-role-update::task_completed", user_id=str(user_id), role_name=role_name)

    except Exception as e:
        logfire.error(
            "agent-role-update::task_failed",
            user_id=str(user_id),
            role_name=role_name,
            error_type=type(e).__name__,
            error_message=str(e)
        )
        # 任务失败，不重新抛出异常（后台任务不应影响主流程）
```

**关键设计要点**:
1. **信号发布时机**：在任务启动的最开始（第一阶段之前）
2. **信号作用**：终止其他正在第一阶段等待的旧任务
3. **第一阶段返回值**：
   - `True`（超时）：没有新任务来抢占，继续执行
   - `False`（收到信号）：有更新的任务启动，当前任务退出
4. **异常处理**：所有异常都被捕获并记录，不会向上传播

## 3.4 错误处理规范

### 可用的异常类型

来自 `<project_work_dir>/api/user_space/file_system/fs_utils/file_object.py`:

- `HybridFileNotFoundError`: 文件不存在或路径不是文件
- `InvalidFileModeError`: 不支持的文件模式
- `LockAcquisitionError`: 无法获取分布式锁
- `S3OperationError`: S3 操作失败（上传/下载）
- `DatabaseOperationError`: 数据库操作失败
- `HybridFileSystemError`: 基础文件系统异常

### 错误处理策略

**任务失败或超时**:
- 确保所有用户空间文件没有进行意外更改
- 不进行重试
- 记录错误日志（使用 logfire.error）
- 如果是第二阶段之后失败，需要将读取到的 `update_cache` 回写到缓存文件

**内存操作失败**:

1. **读取文件失败**（第二阶段）：
   - 捕获异常，不向上抛出
   - 记录 logfire.error，包含文件路径、异常类型和异常信息
   - 区分异常原因：
     - `HybridFileNotFoundError`: 文件不存在，任务终止，**无需回滚**（缓存文件未被修改）
     - `LockAcquisitionError`: 无法获取文件锁，任务终止，**无需回滚**
     - `S3OperationError`: S3 下载失败，任务终止，**无需回滚**
     - `DatabaseOperationError`: 数据库查询失败，任务终止，**无需回滚**
     - 其他异常：记录详细信息，任务终止，**无需回滚**
   - **关键**: 此时 `update_cache` 未成功读取或缓存文件未被清空，因此不执行回滚操作

2. **写入文件失败**（第三阶段审查通过后）：
   - 捕获异常，不向上抛出
   - 记录 logfire.error，包含文件路径、异常类型和异常信息
   - 尝试将读取到的 `update_cache` 回写到缓存文件
   - **回滚操作必须用 try-except 包裹**：
     - 如果回滚也失败，记录 logfire.warning，包含回滚失败的异常信息
     - **绝不重新抛出回滚异常**，避免掩盖原始写入失败异常
   - 任务终止

**Agent 执行失败**:

1. **Agent 未调用工具**：
   - 根据状态控制逻辑重新执行（最多 3 次）
   - 超过最大重试次数后，任务终止
   - 记录 logfire.warning
   - 尝试回滚缓存文件（回滚操作必须用 try-except 包裹）

2. **Agent 输出格式错误**：
   - 捕获异常，记录 logfire.error
   - 任务终止
   - 尝试回滚缓存文件（回滚操作必须用 try-except 包裹）

### 异常处理的关键原则

1. **所有 catch/finally 块中的操作都必须用 try-except 包裹**
2. **回滚操作失败绝不抛出异常**，只记录日志
3. **避免掩盖原始异常**：回滚失败时，原始异常信息仍然是主要的
4. **区分异常原因**：根据不同异常类型采取不同的处理策略
5. **确保任务终止**：任何情况下都不向上抛出异常
6. **文件不存在时不需要回滚**：如果原始异常是 `HybridFileNotFoundError`，说明缓存文件未被修改

### 异常处理代码模式

```python
from api.user_space.file_system.fs_utils.exception import (
    HybridFileNotFoundError,
    LockAcquisitionError,
    S3OperationError,
    DatabaseOperationError,
)
from api.agent.tools.agent_roles.utils import (
    user_agent_role_conversation_strategies_file,
    user_agent_role_concluding_guidence_file,  # 注意拼写：guidence
    user_agent_role_strategies_update_cache_file,
)

async def run_background_update_task(user_id: UUID, role_name: str):
    """执行后台更新任务的入口函数"""
    original_update_cache = None  # 用于跟踪原始缓存内容
    cache_modified = False  # 用于跟踪缓存是否已被修改

    try:
        # 第二阶段：准备文件内容
        try:
            async with user_agent_role_strategies_update_cache_file(user_id, role_name, "r") as f:
                cache_content = f.read().decode("utf-8")
                update_cache = ujson.loads(cache_content) if cache_content else {}
                original_update_cache = update_cache.copy()  # 保存原始内容

            # 提取更新列表
            strategies_list = update_cache.get("strategies_update_cache", [])

            # 检查退出条件
            if not strategies_list:
                logfire.info("agent-role-update::no_updates_pending")
                return  # 没有待处理的更新，正常结束

            # ========== 关键步骤：格式化 strategies_list 为易读文本 ==========
            # 将 strategies_list 数组格式化为 Markdown 格式的文本
            # 以便传递给 Agent A 的 prompt.compile() 方法
            formatted_items = []
            for i, item in enumerate(strategies_list, 1):
                formatted_items.append(
                    f"## 更新请求 {i}\n\n"
                    f"**更新内容**:\n{item['update_content']}\n\n"
                    f"**相关上下文**:\n{item['context']}"
                )
            strategies_update_list = "\n\n".join(formatted_items)
            # ========== 格式化结束 ==========

            # 清空 strategies_update_cache 数组（保留其他 JSON 结构）
            update_cache["strategies_update_cache"] = []
            async with user_agent_role_strategies_update_cache_file(user_id, role_name, "w") as f:
                f.write(ujson.dumps(update_cache).encode("utf-8"))
            cache_modified = True

            # 读取其他文件...
            async with user_agent_role_conversation_strategies_file(user_id, role_name, "r") as f:
                original_strategies = f.read().decode("utf-8")

            async with user_agent_role_concluding_guidance_file(user_id, role_name, "r") as f:
                original_guidance = f.read().decode("utf-8")

            # 调用第三阶段
            await execute_update_phase(
                user_id=user_id,
                role_name=role_name,
                original_strategies=original_strategies,
                original_guidance=original_guidance,
                strategies_update_list=strategies_update_list  # 传入格式化后的文本
            )

        except HybridFileNotFoundError as e:
            logfire.error("agent-role-update::file_not_found",
                         file_path=str(e.file_path) if hasattr(e, 'file_path') else "unknown",
                         error_type="HybridFileNotFoundError",
                         error_message=str(e))
            return  # 文件不存在，缓存未被修改，无需回滚

        except LockAcquisitionError as e:
            logfire.error("agent-role-update::lock_acquisition_failed",
                         error_type="LockAcquisitionError",
                         error_message=str(e))
            return  # 无法获取锁，缓存未被修改，无需回滚

        except (S3OperationError, DatabaseOperationError) as e:
            logfire.error("agent-role-update::file_operation_failed",
                         error_type=type(e).__name__,
                         error_message=str(e))
            return  # 文件操作失败，缓存未被修改或读取未完成，无需回滚

        except Exception as e:
            logfire.error("agent-role-update::unexpected_read_error",
                         error_type=type(e).__name__,
                         error_message=str(e))
            return  # 其他异常，保守处理，无需回滚

        # 注意：第三阶段的异常处理和回滚逻辑在 `phase3_update.py` 中实现
        # 这里通过调用 `execute_update_phase()` 函数已经处理了所有异常

    except Exception as e:
        # 最外层异常捕获（理论上不应该到达这里）
        logfire.error("agent-role-update::unexpected_error",
                     error_type=type(e).__name__,
                     error_message=str(e))
        return
```
```

## 3.5 日志记录规范

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

参考 `<project_work_dir>/api/chat/chat_task.py:157-187` 的实现模式：

- 使用 `LangFuseTraceAttributes` 和 `LangFuseSpanAttributes`
- 使用 `logfire.set_baggage()` 设置 trace 级别的上下文

### 日志记录示例

```python
from api.logger.datamodel import LangFuseTraceAttributes, LangFuseSpanAttributes
from api.logger.time import now_iso
import logfire

async def _run_background_update_task(self, user_id, role_name):
    # 创建 trace 级别的元数据
    langfuse_trace_attributes = LangFuseTraceAttributes(
        name="agent-role-update::background_update_task",
        user_id=str(user_id),
        metadata={
            "role_name": role_name,
        }
    )

    with logfire.set_baggage(**langfuse_trace_attributes.model_dump(mode="json", by_alias=True)) as _:
        # 创建 span
        langfuse_observation_attributes = LangFuseSpanAttributes(
            observation_type="span",
        )

        with logfire.span("agent-role-update::task_start",
                          **langfuse_observation_attributes.model_dump(mode="json", by_alias=True)) as span:

            # 第一阶段：计划更新任务
            logfire.info("agent-role-update::phase1_start",
                        user_id=str(user_id),
                        role_name=role_name)

            # ... 执行第一阶段 ...

            logfire.info("agent-role-update::phase1_complete",
                        user_id=str(user_id),
                        role_name=role_name)

            # 第二阶段：准备文件内容
            logfire.info("agent-role-update::phase2_start",
                        user_id=str(user_id),
                        role_name=role_name)

            try:
                # ... 读取文件 ...
                logfire.info("agent-role-update::files_read_success",
                            files_read=["conversation_strategies.md", "concluding_guidance.md", "strategies_update_cache.json"])
            except Exception as e:
                logfire.error("agent-role-update::files_read_failed",
                            error_message=str(e),
                            error_type=type(e).__name__)
                return

            # 第三阶段：更新任务
            logfire.info("agent-role-update::phase3_start",
                        user_id=str(user_id),
                        role_name=role_name)

            # ... Agent 循环执行 ...

            logfire.info("agent-role-update::task_complete",
                        user_id=str(user_id),
                        role_name=role_name)
```

### 关键日志点

1. 任务开始（`task_start`）
2. 每个阶段开始/完成（`phase1_start`, `phase1_complete`, ...）
3. 文件读取成功/失败（`files_read_success`, `files_read_failed`）
4. 文件写入成功/失败（`files_write_success`, `files_write_failed`）
5. Agent 执行开始/完成（`agent_a_start`, `agent_a_complete`, ...）
6. 审查结果（`review_passed`, `review_failed`）
7. 任务完成/失败（`task_complete`, `task_failed`）
8. 缓存回滚（`cache_rollback`）

## 3.6 外部容器管理策略

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
            # 重试逻辑已在 Agent 函数内部处理
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

        if not agent_b_result["tool_called"]:
            raise RuntimeError("Agent B failed to call edit_guidance tool")

        # 提取 Agent B 的最终结果
        agent_b_result["updated_guidance"] = agent_b_working_guidance["value"]

        # Agent C 执行（审查结果）
        await run_agent_c_review(
            original_strategies=original_strategies,
            original_guidance=original_guidance,
            updated_strategies=agent_a_result["updated_strategies"],
            updated_guidance=agent_b_result["updated_guidance"],
            service_name="default",
            agent_c_result=agent_c_result
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
        raise RuntimeError("Agent A failed to call edit_strategies tool after {MAX_TOOL_CALL_RETRIES} attempts")
```

## 3.7 Agent 完整实现示例

### 3.7.1 Agent A：更新对话策略文件

**文件路径**：`background_update/agents/agent_a_update_strategies.py`

```python
from typing import Callable
from uuid import UUID
from openai.types.chat import ChatCompletionMessageParam
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from pydantic import BaseModel, Field

from api.agent.base_agent import AgentBase
from api.agent.tools.type import ToolClosure
from api.agent.tools.dynamic_tool_DI.constructor import construct_tool
from api.workflow.langfuse_prompt_template.constant import _get_prompt_from_langfuse
from ..models import (
    AgentAResult,
    MAX_TOOL_CALL_RETRIES,
)
from api.agent.tools.read_file.utils import read_from_string
from api.agent.tools.edit_file.utils import edit_string
import logfire


# ========== 工具参数定义 ==========

class ReadStrategiesPartToolParam(BaseModel):
    """读取对话策略的部分内容"""
    offset: int = Field(default=0, ge=0, description="起始行号（从 0 开始）")
    limit: int = Field(default=100, ge=1, le=1000, description="读取的行数")


class EditStrategiesToolParam(BaseModel):
    """编辑对话策略内容"""
    old_text: str = Field(..., description="要替换的原始文本")
    new_text: str = Field(..., description="替换后的新文本")
    replace_all: bool = Field(default=False, description="是否替换所有出现（默认只替换第一个）")


# ========== Agent 函数实现 ==========

async def run_agent_a_update_strategies(
    original_strategies: str,
    strategies_update_list: str,
    review_suggestions: str | None,
    service_name: str,
    agent_a_working_strategies: dict[str, str],
    agent_a_result: AgentAResult
) -> None:
    """
    Agent A: 更新对话策略文件

    执行流程:
    1. 获取并编译 Langfuse 提示词模板
    2. 构造两个动态工具：read_strategies_part 和 edit_strategies
    3. 构造 OpenAI 格式的记忆（memories）
    4. 初始化 AgentBase
    5. 执行 Agent（带重试逻辑）
    6. 检查工具调用状态

    参数:
        original_strategies: 原始的对话策略内容
        strategies_update_list: 格式化后的更新请求文本
        review_suggestions: Agent C 的审查建议（第一轮为 None）
        service_name: LLM 服务名称
        agent_a_working_strategies: 工作容器（可变 dict，由工具闭包捕获并修改）
        agent_a_result: 结果容器（TypedDict，存储执行状态和最终结果）
    """

    # ========== 步骤1: 获取并编译提示词 ==========
    prompt = await _get_prompt_from_langfuse("agent-role-update/update-strategies")
    if not prompt:
        raise ValueError("Langfuse prompt not found: agent-role-update/update-strategies")

    system_prompt = prompt.compile({
        "original_strategies": original_strategies,
        "strategies_update_cache": strategies_update_list,
        "review_suggestions": review_suggestions or ""
    })

    # ========== 步骤2: 构造动态工具 ==========
    tool_define_list: list[ChatCompletionToolParam] = []
    tool_call_function: dict[str, ToolClosure] = {}

    # 工具1: read_strategies_part
    tool_define_1, tool_closure_1 = construct_tool(
        tool_name="read_strategies_part",
        tool_description=(
            "读取对话策略文件的部分内容，帮助了解当前策略的具体内容。"
            "可以通过 offset 和 limit 参数控制读取的范围。"
        ),
        tool_param_model=ReadStrategiesPartToolParam,
        call_back=lambda param: read_from_string(
            agent_a_working_strategies["value"],
            offset=param.offset,
            limit=param.limit,
            add_line_numbers=True
        )
    )
    tool_define_list.append(tool_define_1)
    tool_call_function["read_strategies_part"] = tool_closure_1

    # 工具2: edit_strategies
    async def edit_strategies_callback(param: EditStrategiesToolParam) -> None:
        """编辑对话策略的工作变量"""
        try:
            agent_a_working_strategies["value"] = edit_string(
                string=agent_a_working_strategies["value"],
                old_text=param.old_text,
                new_text=param.new_text,
                replace_all=param.replace_all
            )
            agent_a_result["tool_called"] = True
            logfire.info("agent-role-update::agent_a_edit_success")
        except ValueError as e:
            logfire.error("agent-role-update::agent_a_edit_failed", error=str(e))
            raise

    tool_define_2, tool_closure_2 = construct_tool(
        tool_name="edit_strategies",
        tool_description=(
            "编辑对话策略的内容。使用 old_text 和 new_text 参数进行文本替换。"
            "如果 old_text 在文件中出现多次，需要设置 replace_all=True。"
        ),
        tool_param_model=EditStrategiesToolParam,
        call_back=edit_strategies_callback
    )
    tool_define_list.append(tool_define_2)
    tool_call_function["edit_strategies"] = tool_closure_2

    # ========== 步骤3: 构造 memories ==========
    memories: list[ChatCompletionMessageParam] = [
        {
            "role": "system",
            "content": system_prompt
        },
        {
            "role": "user",
            "content": (
                "请根据提供的更新请求，更新对话策略文件。\n\n"
                "执行步骤：\n"
                "1. 首先使用 read_strategies_part 工具了解当前策略的内容\n"
                "2. 然后使用 edit_strategies 工具进行必要的修改\n"
                "3. 可以多次调用 edit_strategies 工具完成多个修改\n\n"
                "注意事项：\n"
                "- 保持原有的格式和结构\n"
                "- 确保更新后的策略连贯一致\n"
                "- 如果有审查建议，请根据建议进行修改"
            )
        }
    ]

    # ========== 步骤4: 初始化 AgentBase ==========
    agent = AgentBase(
        tools=tool_define_list,
        tool_call_function=tool_call_function
    )

    # ========== 步骤5: 执行 Agent（带重试逻辑） ==========
    for attempt in range(MAX_TOOL_CALL_RETRIES):
        if attempt > 0:
            logfire.warning(
                "agent-role-update::agent_a_retry",
                attempt=attempt,
                max_retries=MAX_TOOL_CALL_RETRIES
            )
            # 重置工作容器和状态
            agent_a_working_strategies["value"] = original_strategies
            agent_a_result["tool_called"] = False

        with logfire.span("agent-role-update::agent_a_execution", attempt=attempt):
            new_memories, new_messages = await agent.run(
                memories=memories,
                service_name=service_name,
                thinking=True
            )

        # 检查是否成功调用工具
        if agent_a_result["tool_called"]:
            logfire.info("agent-role-update::agent_a_success")
            break

    # ========== 步骤6: 检查最终状态 ==========
    if not agent_a_result["tool_called"]:
        logfire.error("agent-role-update::agent_a_failed_after_retries")
        raise RuntimeError(f"Agent A failed to call edit_strategies tool after {MAX_TOOL_CALL_RETRIES} attempts")
```

### 3.7.2 Agent B：更新对话总结指导文件

**文件路径**：`background_update/agents/agent_b_update_guidance.py`

```python
from typing import Callable
from openai.types.chat import ChatCompletionMessageParam
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from pydantic import BaseModel, Field

from api.agent.base_agent import AgentBase
from api.agent.tools.type import ToolClosure
from api.agent.tools.dynamic_tool_DI.constructor import construct_tool
from api.workflow.langfuse_prompt_template.constant import _get_prompt_from_langfuse
from ..models import (
    AgentBResult,
    MAX_TOOL_CALL_RETRIES,
)
from api.agent.tools.read_file.utils import read_from_string
from api.agent.tools.edit_file.utils import edit_string
import logfire


# ========== 工具参数定义 ==========

class ReadGuidancePartToolParam(BaseModel):
    """读取对话总结指导的部分内容"""
    offset: int = Field(default=0, ge=0, description="起始行号（从 0 开始）")
    limit: int = Field(default=100, ge=1, le=1000, description="读取的行数")


class EditGuidanceToolParam(BaseModel):
    """编辑对话总结指导内容"""
    old_text: str = Field(..., description="要替换的原始文本")
    new_text: str = Field(..., description="替换后的新文本")
    replace_all: bool = Field(default=False, description="是否替换所有出现")


# ========== Agent 函数实现 ==========

async def run_agent_b_update_guidance(
    updated_strategies: str,
    original_guidance: str,
    review_suggestions: str | None,
    service_name: str,
    agent_b_working_guidance: dict[str, str],
    agent_b_result: AgentBResult
) -> None:
    """
    Agent B: 更新对话总结指导文件

    执行流程:
    1. 获取并编译 Langfuse 提示词模板
    2. 构造两个动态工具：read_guidance_part 和 edit_guidance
    3. 构造 OpenAI 格式的记忆（memories）
    4. 初始化 AgentBase
    5. 执行 Agent（带重试逻辑）
    6. 检查工具调用状态

    参数:
        updated_strategies: Agent A 更新后的对话策略（作为上下文）
        original_guidance: 原始的对话总结指导内容
        review_suggestions: Agent C 的审查建议（第一轮为 None）
        service_name: LLM 服务名称
        agent_b_working_guidance: 工作容器（可变 dict，由工具闭包捕获并修改）
        agent_b_result: 结果容器（TypedDict，存储执行状态和最终结果）
    """

    # ========== 步骤1: 获取并编译提示词 ==========
    prompt = await _get_prompt_from_langfuse("agent-role-update/update-guidance")
    if not prompt:
        raise ValueError("Langfuse prompt not found: agent-role-update/update-guidance")

    system_prompt = prompt.compile({
        "updated_strategies": updated_strategies,
        "original_guidance": original_guidance,
        "review_suggestions": review_suggestions or ""
    })

    # ========== 步骤2: 构造动态工具 ==========
    tool_define_list: list[ChatCompletionToolParam] = []
    tool_call_function: dict[str, ToolClosure] = {}

    # 工具1: read_guidance_part
    tool_define_1, tool_closure_1 = construct_tool(
        tool_name="read_guidance_part",
        tool_description=(
            "读取对话总结指导文件的部分内容，帮助了解当前指导的具体内容。"
            "可以通过 offset 和 limit 参数控制读取的范围。"
        ),
        tool_param_model=ReadGuidancePartToolParam,
        call_back=lambda param: read_from_string(
            agent_b_working_guidance["value"],
            offset=param.offset,
            limit=param.limit,
            add_line_numbers=True
        )
    )
    tool_define_list.append(tool_define_1)
    tool_call_function["read_guidance_part"] = tool_closure_1

    # 工具2: edit_guidance
    async def edit_guidance_callback(param: EditGuidanceToolParam) -> None:
        """编辑对话总结指导的工作变量"""
        try:
            agent_b_working_guidance["value"] = edit_string(
                string=agent_b_working_guidance["value"],
                old_text=param.old_text,
                new_text=param.new_text,
                replace_all=param.replace_all
            )
            agent_b_result["tool_called"] = True
            logfire.info("agent-role-update::agent_b_edit_success")
        except ValueError as e:
            logfire.error("agent-role-update::agent_b_edit_failed", error=str(e))
            raise

    tool_define_2, tool_closure_2 = construct_tool(
        tool_name="edit_guidance",
        tool_description=(
            "编辑对话总结指导的内容。使用 old_text 和 new_text 参数进行文本替换。"
            "如果 old_text 在文件中出现多次，需要设置 replace_all=True。"
        ),
        tool_param_model=EditGuidanceToolParam,
        call_back=edit_guidance_callback
    )
    tool_define_list.append(tool_define_2)
    tool_call_function["edit_guidance"] = tool_closure_2

    # ========== 步骤3: 构造 memories ==========
    memories: list[ChatCompletionMessageParam] = [
        {
            "role": "system",
            "content": system_prompt
        },
        {
            "role": "user",
            "content": (
                "请根据更新后的对话策略，更新对话总结指导文件。\n\n"
                "执行步骤：\n"
                "1. 首先使用 read_guidance_part 工具了解当前指导的内容\n"
                "2. 然后使用 edit_guidance 工具进行必要的修改\n"
                "3. 可以多次调用 edit_guidance 工具完成多个修改\n\n"
                "注意事项：\n"
                "- 确保指导内容与更新后的策略保持一致\n"
                "- 保持原有的格式和结构\n"
                "- 如果有审查建议，请根据建议进行修改"
            )
        }
    ]

    # ========== 步骤4: 初始化 AgentBase ==========
    agent = AgentBase(
        tools=tool_define_list,
        tool_call_function=tool_call_function
    )

    # ========== 步骤5: 执行 Agent（带重试逻辑） ==========
    for attempt in range(MAX_TOOL_CALL_RETRIES):
        if attempt > 0:
            logfire.warning(
                "agent-role-update::agent_b_retry",
                attempt=attempt,
                max_retries=MAX_TOOL_CALL_RETRIES
            )
            # 重置工作容器和状态
            agent_b_working_guidance["value"] = original_guidance
            agent_b_result["tool_called"] = False

        with logfire.span("agent-role-update::agent_b_execution", attempt=attempt):
            new_memories, new_messages = await agent.run(
                memories=memories,
                service_name=service_name,
                thinking=True
            )

        # 检查是否成功调用工具
        if agent_b_result["tool_called"]:
            logfire.info("agent-role-update::agent_b_success")
            break

    # ========== 步骤6: 检查最终状态 ==========
    if not agent_b_result["tool_called"]:
        logfire.error("agent-role-update::agent_b_failed_after_retries")
        raise RuntimeError(f"Agent B failed to call edit_guidance tool after {MAX_TOOL_CALL_RETRIES} attempts")
```

### 3.7.3 Agent C：审查更新结果

**文件路径**：`background_update/agents/agent_c_review.py`

```python
import difflib
from openai.types.chat import ChatCompletionMessageParam
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from pydantic import BaseModel, Field

from api.agent.base_agent import AgentBase
from api.agent.tools.type import ToolClosure
from api.agent.tools.dynamic_tool_DI.constructor import construct_tool
from api.workflow.langfuse_prompt_template.constant import _get_prompt_from_langfuse
from ..models import (
    AgentCResult,
)
import logfire


# ========== 辅助函数 ==========

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


# ========== 工具参数定义 ==========

class SubmitReviewToolParam(BaseModel):
    """提交审查结果"""
    score: int = Field(..., ge=0, le=100, description="审查分数（0-100）")
    suggestions: str = Field(default="", description="修改建议（如果不通过）")


# ========== Agent 函数实现 ==========

async def run_agent_c_review(
    original_strategies: str,
    original_guidance: str,
    updated_strategies: str,
    updated_guidance: str,
    service_name: str,
    agent_c_result: AgentCResult
) -> None:
    """
    Agent C: 审查更新结果

    执行流程:
    1. 生成 strategies_diff 和 guidance_diff
    2. 获取并编译 Langfuse 提示词模板
    3. 构造动态工具：submit_review_result
    4. 构造 OpenAI 格式的记忆（memories）
    5. 初始化 AgentBase
    6. 执行 Agent（不需要重试，只执行一次）

    参数:
        original_strategies: 原始的对话策略
        original_guidance: 原始的对话总结指导
        updated_strategies: Agent A 更新后的对话策略
        updated_guidance: Agent B 更新后的对话总结指导
        service_name: LLM 服务名称
        agent_c_result: 结果容器（TypedDict，存储审查分数和建议）
    """

    # ========== 步骤1: 生成 diff ==========
    strategies_diff = generate_diff(
        original_strategies,
        updated_strategies,
        "conversation_strategies.md"
    )
    guidance_diff = generate_diff(
        original_guidance,
        updated_guidance,
        "concluding_guidance.md"
    )

    logfire.info(
        "agent-role-update::agent_c_diff_generated",
        strategies_diff_lines=strategies_diff.count('\n'),
        guidance_diff_lines=guidance_diff.count('\n')
    )

    # ========== 步骤2: 获取并编译提示词 ==========
    prompt = await _get_prompt_from_langfuse("agent-role-update/review-updates")
    if not prompt:
        raise ValueError("Langfuse prompt not found: agent-role-update/review-updates")

    system_prompt = prompt.compile({
        "strategies_diff": strategies_diff,
        "guidance_diff": guidance_diff
    })

    # ========== 步骤3: 构造动态工具 ==========
    async def submit_review_callback(param: SubmitReviewToolParam) -> None:
        """提交审查结果"""
        agent_c_result["score"] = param.score
        agent_c_result["suggestions"] = param.suggestions
        logfire.info(
            "agent-role-update::agent_c_review_submitted",
            score=param.score,
            has_suggestions=bool(param.suggestions)
        )

    tool_define, tool_closure = construct_tool(
        tool_name="submit_review_result",
        tool_description=(
            "提交对更新内容的审查结果。"
            "根据更新的质量给出 0-100 分的评分，"
            "并给出具体的修改建议（如果评分低于 80 分）。"
        ),
        tool_param_model=SubmitReviewToolParam,
        call_back=submit_review_callback
    )

    # ========== 步骤4: 构造 memories ==========
    memories: list[ChatCompletionMessageParam] = [
        {
            "role": "system",
            "content": system_prompt
        },
        {
            "role": "user",
            "content": (
                "请审查对话策略和总结指导的更新内容。\n\n"
                "审查标准：\n"
                "1. 更新是否准确反映了用户的请求\n"
                "2. 内容是否连贯一致\n"
                "3. 格式是否规范\n"
                "4. 是否存在遗漏或错误\n\n"
                "评分标准：\n"
                "- 80-100 分：优秀，可以通过\n"
                "- 60-79 分：良好，但需要修改\n"
                "- 0-59 分：不合格，需要重新修改\n\n"
                "审查完成后，请调用 submit_review_result 工具提交结果。"
            )
        }
    ]

    # ========== 步骤5: 初始化 AgentBase ==========
    agent = AgentBase(
        tools=[tool_define],
        tool_call_function={
            "submit_review_result": tool_closure
        }
    )

    # ========== 步骤6: 执行 Agent ==========
    with logfire.span("agent-role-update::agent_c_execution"):
        new_memories, new_messages = await agent.run(
            memories=memories,
            service_name=service_name,
            thinking=True
        )

    logfire.info(
        "agent-role-update::agent_c_completed",
        score=agent_c_result["score"],
        pass_threshold=agent_c_result["score"] >= 80
    )
```

## 相关实现文档

- [上下文文档](./background_update_task_spec_context.md)
- [设计文档](./background_update_task_spec_design.md)
- [审核文档](./background_update_task_spec_review.md)
