# 角色对话策略更新功能 - 实现文档

---
文档标题：background_update_task_spec_implementation
文档描述：本文档描述角色对话策略更新功能的实现细节，包括代码基础设施、文件夹结构、任务触发、错误处理、日志记录、容器管理和 Agent 实现示例。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [可用的代码基础设施](#可用的代码基础设施)
    - [AgentBase](#agentbase)
    - [动态工具 DI](#动态工具-di)
    - [Langfuse 提示词模板](#langfuse-提示词模板)
    - [Redis 分布式锁](#redis-分布式锁)
    - [Redis 发布订阅](#redis-发布订阅)

## 可用的代码基础设施

### AgentBase

**文件路径**: `../../../../api/agent/base_agent.py`

**核心方法**: `async def run(memories, service_name, thinking=True)`

**参数**:
- `memories`: 对话历史（`list[ChatCompletionMessageParam]`）
- `service_name`: 使用的 LLM 服务名称
- `thinking`: 是否启用思考模式（默认 `True`）

**返回**: `(new_memories, new_messages)` 元组

**循环控制**: 通过 `loop_control` 参数和生命周期方法控制循环行为

### 动态工具 DI

**文档路径**: `../../../../docs/for_LLM_dev/dynamic_tool_DI的设计和使用.md`

**核心函数**: `construct_tool(tool_name, tool_description, tool_param_model, call_back)`

**输入**:
- `tool_name`: str - AI 调用时使用的工具名
- `tool_description`: str - 告诉 AI 这个工具干什么
- `tool_param_model`: type[BaseModel] - Pydantic 模型，定义参数结构
- `call_back`: Callable - 业务逻辑函数（async）

**输出**: `(tool_define, tool_closure)` 元组
- `tool_define`: `ChatCompletionToolParam` - 给 AI 看的工具定义
- `tool_closure`: `ToolClosure` - 程序实际执行的闭包

### Langfuse 提示词模板

**模块路径**: `../../../../api/workflow/langfuse_prompt_template`

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

# 1. 获取提示词模板（注意：这是同步函数，不需要 await）
prompt = _get_prompt_from_langfuse("agent-role-update/update-strategies")
if not prompt:
    raise ValueError("Prompt not found in Langfuse")

# 2. 编译提示词（传入业务参数，使用关键字参数）
system_prompt = prompt.compile(
    original_strategies=original_strategies,
    strategies_update_cache=strategies_update_list,
    review_suggestions=review_suggestions or ""
)

# 3. 构造 OpenAI 格式的记忆
memories = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": "请根据上下文更新对话策略"}
]
```

**已配置的提示词路径**:
- Agent A: `"agent-role-update/update-strategies"`
- Agent B: `"agent-role-update/update-conclusion-guidance"`
- Agent C: `"agent-role-update/review-updates"`

### Redis 分布式锁

**文件路径**: `../../../../api/redis/distributed_lock.py`

**类**: `RedisDistributedLock`

**使用方式**: `async with RedisDistributedLock(key, timeout=30) as lock:`

### Redis 发布订阅

**文件路径**: `../../../../api/redis/pubsub.py`

**发布**: `await publish_event(channel)`

**订阅**: `subscribe_to_event()` 会阻塞直到收到消息，必须作为后台任务运行：

```python
# 创建订阅任务（在后台运行）
subscribe_task = asyncio.create_task(subscribe_to_event(channel, event))

# 等待信号，超时时间为 30 秒
try:
    await asyncio.wait_for(event.wait(), timeout=30)
finally:
    # 取消订阅任务
    subscribe_task.cancel()
    try:
        await subscribe_task
    except asyncio.CancelledError:
        pass
```

## 相关实现文档

- [文件夹结构设计](./02_folder_structure.md)
- [任务触发规范](./03_task_triggering.md)
- [错误处理规范](./04_error_handling.md)
- [日志记录规范](./05_logging.md)
- [外部容器管理策略](./06_container_management.md)
- [Agent 实现示例](./07_agent_implementations/)
- [上下文文档](../background_update_task_spec_context.md)
- [设计文档](../background_update_task_spec_design.md)
