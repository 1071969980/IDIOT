---
文档标题：mem_maintainer_agents_spec_code_snippets
文档描述：记忆维护Agent系统的关键代码片段和类设计说明
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [概述](#概述)
- [XML 标记扩展](#xml-标记扩展)
- [return_memory_recall 工具定义](#return_memory_recall-工具定义)
  - [参数模型与 GENERATION_TOOL_PARAM](#参数模型与-generation_tool_param)
  - [工具闭包](#工具闭包)
- [生命周期钩子](#生命周期钩子)
  - [inject_memory_recall_context](#inject_memory_recall_context)
  - [inject_return_memory_recall_closure](#inject_return_memory_recall_closure)
  - [inject_memory_write_context](#inject_memory_write_context)
- [Agent 类定义](#agent-类定义)
  - [MemRecallAgent](#memrecallagent)
  - [MemWriteAgent](#memwriteagent)
- [MEMORY.md 发现辅助函数](#memorymd-发现辅助函数)
- [main_agent_strategy 集成](#main_agent_strategy-集成)
- [Session Event 扩展](#session-event-扩展)

---

## 概述

本文档包含记忆维护 Agent 系统的关键代码片段，涵盖新增常量、工具定义、闭包构造、生命周期钩子、Agent 类和策略集成。每个片段侧重表达概念性设计，非完整实现。

设计上下文参见 [design 文档](./mem_maintainer_agents_spec_design.md)，代码基础设施参见 [context 文档](./mem_maintainer_agents_spec_context.md)。

---

## XML 标记扩展

在 `api/agent/xml_marks_def.py` 中新增记忆召回内容块标记：

```python
# api/agent/xml_marks_def.py — 新增
MEMORY_RECALL_BLOCK_START = "<memory_recall>"
MEMORY_RECALL_BLOCK_END = "</memory_recall>"
```

用于 `return_memory_recall` 闭包包裹记忆文件内容，在上下文中提供明确的语义边界。

## return_memory_recall 工具定义

### 参数模型与 GENERATION_TOOL_PARAM

工具文件组织于 `api/agent/tools/memory_recall/` 下，参数定义遵循 `summarization_compact` 的模式（参见 `api/agent/tools/summarization_compact/config_data_model.py`）：

```python
# api/agent/tools/memory_recall/config_data_model.py
TOOL_NAME = "return_memory_recall"

class ReturnMemoryRecallParamDefine(BaseModel):
    target_marker: str = Field(
        default="major",
        description="目标 Marker 名称，召回结果将追加到此 Marker",
    )
    mem_files: list[str] = Field(
        ...,
        description="需要召回的记忆文件绝对路径列表",
    )
    additional_msg: str | None = Field(
        default=None,
        description="附加说明文本，可补充召回理由或上下文",
    )

GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name=TOOL_NAME,
        description=(
            "将检索到的记忆文件内容召回并注入到指定 Marker。"
            "读取 mem_files 中每个文件的内容，用 <memory_recall> 标记包裹后推送到目标 Marker。"
        ),
        parameters=turn_pydantic_model_to_json_schema(ReturnMemoryRecallParamDefine),
    ),
)
```

### 工具闭包

闭包捕获 `memory_trails` 和 `juicefs_backend`（用于读取文件内容）：

```python
# api/agent/tools/memory_recall/tool_closure.py
def make_return_memory_recall_closure(
    memory_trails: MemoryTrails,
    juicefs_backend: "JuiceFSBackend",
) -> ToolClosure:
    async def closure(**kwargs) -> ToolTaskResult:
        param = ReturnMemoryRecallParamDefine.model_validate(kwargs)
        target = param.target_marker

        # 读取 mem_files 内容并组装消息
        parts = []
        for file_path in param.mem_files:
            content, _, _ = await juicefs_backend.read_file(file_path)
            parts.append(f"### {file_path}\n{content}")

        body = "\n\n".join(parts)
        if param.additional_msg:
            body = f"{param.additional_msg}\n\n{body}"

        msg = ChatCompletionSystemMessageParam(
            role="system",
            content=f"{MEMORY_RECALL_BLOCK_START}\n{body}\n{MEMORY_RECALL_BLOCK_END}",
        )
        memory_trails.append_to_marker(target, msg, is_new=True, to_agent_msg=True)
        return ToolTaskResult(
            str_content=f"已将 {len(param.mem_files)} 个记忆文件注入到 {target} Marker"
        )
    return closure
```

---

## 生命周期钩子

### inject_memory_recall_context

在 `on_agent_start` 阶段注入记忆召回上下文，包含三部分：工作要求、MEMORY.md 索引、工具参数与限制。

> **`mem_marker_name` 语义说明**：此参数值为 MemRecallAgent 的执行 marker（格式为 `mem_recall:<uuid>`，例如 `mem_recall:01912abc-def4-7abc-8def-123456789abc`）。上下文消息将被注入到此 marker，即 MemRecallAgent 的对话起点。

```python
# api/agent/tools/memory_recall/lifecycle_hooks.py
@lifecycle_hook("on_agent_start", position="after")
async def inject_memory_recall_context(
    self: "AgentBase", mem_marker_name: str,
) -> None:
    # 1. 发现并读取 MEMORY.md 索引文件
    memory_indices = await discover_memory_index_files(
        self.tool_init_res.allowed_rel_dirs_in_juicefs_for_tool,
        self.tool_init_res,
    )
    # 2. 组合上下文消息：工作要求 + 索引内容
    context_parts = _build_recall_context_parts(memory_indices)

    # 3. 将 GENERATION_TOOL_PARAM 工具定义以 TOOL_DISCOVERY_RESULT_BLOCK
    #    包裹后注入上下文，使 LLM 能发现并识别 return_memory_recall 工具。
    #    这与 prepare_tool_closures 注入的实际闭包配合完成调用链：
    #    上下文提供工具定义（签名、参数说明）→ 闭包提供可执行实现。
    tool_disclosure = (
        f"{TOOL_DISCOVERY_RESULT_BLOCK_START}\n"
        f"{GENERATION_TOOL_PARAM.model_dump_json(indent=2)}\n"
        f"{TOOL_DISCOVERY_RESULT_BLOCK_END}"
    )
    context_parts.append(tool_disclosure)

    context_msg = ChatCompletionSystemMessageParam(
        role="system",
        content="\n\n".join(context_parts),
    )
    self._memory_trails.append_to_marker(
        mem_marker_name, context_msg, is_new=True, to_agent_msg=False,
    )
    # 4. 设置 tool steering：只允许只读工具 + return_memory_recall
    read_only_tools = {"read_file", "list_directory", "get_item_type"}
    self.set_tool_choice_steering(read_only_tools | {TOOL_NAME})
```

### inject_return_memory_recall_closure

在 `prepare_tool_closures` 阶段构造并注入闭包：

```python
@lifecycle_hook("prepare_tool_closures", modifies_return=True, position="after")
async def inject_return_memory_recall_closure(
    self: "AgentBase",
    closures: dict[str, "ToolClosure"],
    mem_marker_name: str,
) -> dict[str, "ToolClosure"]:
    juicefs_backend = _get_juicefs_backend(self.tool_init_res)
    closures[TOOL_NAME] = make_return_memory_recall_closure(
        memory_trails=self._memory_trails,
        juicefs_backend=juicefs_backend,
    )
    return closures
```

### inject_memory_write_context

MemWriteAgent 的上下文注入，结构与 recall 类似但不注入专属工具：

```python
# api/agent/tools/memory_write/lifecycle_hooks.py
@lifecycle_hook("on_agent_start", position="after")
async def inject_memory_write_context(
    self: "AgentBase", mem_marker_name: str,
) -> None:
    memory_indices = await discover_memory_index_files(
        self.tool_init_res.allowed_rel_dirs_in_juicefs_for_tool,
        self.tool_init_res,
    )
    context_msg = _build_write_context_msg(memory_indices)
    self._memory_trails.append_to_marker(
        mem_marker_name, context_msg, is_new=True, to_agent_msg=False,
    )
    # 允许读写工具 + bash
    write_tools = {"read_file", "write_file", "list_directory", "get_item_type", "bash"}
    self.set_tool_choice_steering(write_tools)
```

---

## Agent 类定义

### MemRecallAgent

继承 `AgentBase`，注册两个钩子（context + closure），不使用 StreamingProcessor。类定义位于 `api/agent/strategy/mem_recall_agent.py`。

```python
@agent_decorator(inject_memory_recall_context, inject_return_memory_recall_closure)
class MemRecallAgent(AgentBase):
    def __init__(self, user_id, session_id, session_task_id,
                 cancel_event, tool_init_res, **kwargs):
        super().__init__(cancel_event, tool_init_res)
        self.user_id = user_id
        self.session_id = session_id
        self.session_task_id = session_task_id
        self._session_task = None

    @property
    async def session_task(self):
        if self._session_task is None:
            self._session_task = await get_task(self.session_task_id)
        return self._session_task

    @property
    def recommend_memory_recall_target_marker(self) -> str:
        """推荐的目标 Marker，默认 "major"（即主 Agent 的工作 Marker）。"""
        return "major"
```

### MemWriteAgent

结构与 MemRecallAgent 一致，但只注册 context 钩子，无专属工具闭包：

```python
@agent_decorator(inject_memory_write_context)
class MemWriteAgent(AgentBase):
    def __init__(self, user_id, session_id, session_task_id,
                 cancel_event, tool_init_res, **kwargs):
        super().__init__(cancel_event, tool_init_res)
        self.user_id = user_id
        self.session_id = session_id
        self.session_task_id = session_task_id
        self._session_task = None

    @property
    async def session_task(self):
        if self._session_task is None:
            self._session_task = await get_task(self.session_task_id)
        return self._session_task
```

---

## MEMORY.md 发现辅助函数

统一的辅助函数，供 recall 和 write 的 context 钩子共用。位于 `api/agent/tools/memory_utils.py`：

```python
# api/agent/tools/memory_utils.py
async def discover_memory_index_files(
    allowed_rel_dirs: set[PurePosixPath],
    tool_init_res: "ToolInitializationResult",
) -> list[str]:
    """从允许的相对路径中发现 /dist_fs/sys/memory/ 下的 MEMORY.md 文件内容。

    Returns:
        list[str]: 命中的 MEMORY.md 文件的**内容列表**（非路径列表）。
                  每个 str 元素为一份 MEMORY.md 的完整文本内容。

    路径发现逻辑：
    1. allowed_rel_dirs → 拼接 /dist_fs 前缀 → 得到绝对路径
    2. 过滤：仅保留 /dist_fs/sys/memory/ 子路径
    3. 对命中路径检查 MEMORY.md 是否存在，存在则读取内容
    """
    memory_root = PurePosixPath("/dist_fs/sys/memory")
    backend = _get_juicefs_backend(tool_init_res)
    found = []
    for rel_dir in allowed_rel_dirs:
        abs_path = PurePosixPath("/dist_fs") / rel_dir
        try:
            abs_path.relative_to(memory_root)
        except ValueError:
            continue
        memory_md = abs_path / "MEMORY.md"
        if await backend.file_exists(str(memory_md)):
            content, _, _ = await backend.read_file(str(memory_md))
            found.append(content)
    return found
```

---

## main_agent_strategy 集成

修改 `api/agent/strategy/main_agent_strategy.py`，在主 Agent 执行前后插入记忆维护阶段。三阶段流程：记忆召回（同步前置） → 主 Agent 执行 → 后台记忆写入。

```python
async def main_agent_strategy(
    user_id, session_id, session_task_id, session_branch_name,
    system_mem, memories, tool_init_res, service_name,
    streaming_processor, cancel_event, **kwargs,
):
    trails = MemoryTrails()
    trails.create_marker("base", memories)
    trails.fork_marker("base", "major")

    # === 阶段1：记忆召回（同步前置） ===
    should_recall = _should_run_memory_recall(tool_init_res, memories)
    if should_recall:
        recall_agent = MemRecallAgent(
            user_id, session_id, session_task_id,
            cancel_event, tool_init_res,
        )
        recall_agent._memory_trails = trails  # 共享 MemoryTrails
        recall_uuid = str(uuid7())
        trails.fork_marker("base", f"mem_recall:{recall_uuid}")

        await publish_SSE_session_event(session_id, _mem_recall_started_event(...))
        try:
            with logfire.span("memory_recall"):
                await recall_agent.run(f"mem_recall:{recall_uuid}", service_name)
        except Exception:
            trails.append_to_marker("major", _fallback_recall_msg(), is_new=True)
        await publish_SSE_session_event(session_id, _mem_recall_completed_event(...))

    # === 阶段2：主 Agent 执行 ===
    agent = MainAgent(...)
    agent._system_mem = system_mem
    agent._memory_trails = trails
    await agent.run("major", service_name)

    # === 阶段3：后台记忆写入 ===
    should_write = _should_run_memory_write(tool_init_res, memories)
    if should_write:
        write_agent = MemWriteAgent(
            user_id, session_id, session_task_id,
            cancel_event, tool_init_res,
        )
        write_agent._memory_trails = trails
        write_uuid = str(uuid7())
        trails.fork_marker("base", f"mem_write:{write_uuid}")

        async def _run_write_background():
            await publish_SSE_session_event(session_id, _mem_write_started_event(...))
            with logfire.span("memory_write"):
                await write_agent.run(f"mem_write:{write_uuid}", service_name)
            await publish_SSE_session_event(session_id, _mem_write_completed_event(...))

        asyncio.create_task(_run_write_background())

    mem_creates = trails.extract_db_create_data("major", user_id, session_id, session_task_id)
    agent_messages = trails.extract_agent_messages("major", user_id, session_id, session_task_id)
    # 注意：MemWriteAgent 的对话不需要持久化到 DB，仅其文件操作副作用有意义。
    # 因此 extract_db_create_data 仅从 major Marker 提取，不涉及 mem_write Marker。
    return mem_creates, agent_messages
```

关键设计要点：
- MemRecallAgent 和 MemWriteAgent 均共享主 Agent 的 `MemoryTrails` 实例
- 召回结果通过 `return_memory_recall` 闭包的 `append_to_marker("major", ...)` 直接写入主 Agent 的 major Marker
- 写入阶段通过 `asyncio.create_task` 非阻塞执行
- 每个 Agent 使用 `fork_marker` 从 base 分叉独立 Marker

---

## Session Event 扩展

在 `api/chat/session_event_streaming/event_types.py` 中扩展事件类型和载荷：

```python
SessionEventType = Literal[
    "heartbeat",
    "branch_task_started",
    "branch_task_completed",
    "mem_recall_started",      # 新增
    "mem_recall_completed",    # 新增
    "mem_write_started",       # 新增
    "mem_write_completed",     # 新增
]

class MemRecallStartedEventPayload(BaseModel):
    session_task_id: UUID

class MemRecallCompletedEventPayload(BaseModel):
    session_task_id: UUID
    has_exception: bool

class MemWriteStartedEventPayload(BaseModel):
    session_task_id: UUID

class MemWriteCompletedEventPayload(BaseModel):
    session_task_id: UUID
    has_exception: bool

# 更新 SessionEventPayloadType 联合类型，将新增 Payload 纳入
SessionEventPayloadType = (
    BranchTaskStartedEventPayload
    | BranchTaskCompletedEventPayload
    | HeartbeatEventPayload
    | MemRecallStartedEventPayload
    | MemRecallCompletedEventPayload
    | MemWriteStartedEventPayload
    | MemWriteCompletedEventPayload
)
```

为每个新增 Payload 创建对应的 `SessionEventBase` 子类，并注册到事件分发映射中。事件通过 `publish_SSE_session_event`（参见 `api/chat/session_event_streaming/publisher.py`）发送，用于前端展示记忆维护进度。

---

## 相关文件索引

| 文件路径 | 角色 |
|----------|------|
| `api/agent/xml_marks_def.py` | 新增 MEMORY_RECALL_BLOCK 标记 |
| `api/agent/tools/memory_recall/config_data_model.py` | return_memory_recall 参数与 TOOL_PARAM |
| `api/agent/tools/memory_recall/tool_closure.py` | return_memory_recall 闭包构造 |
| `api/agent/tools/memory_recall/lifecycle_hooks.py` | MemRecallAgent 生命周期钩子 |
| `api/agent/tools/memory_write/lifecycle_hooks.py` | MemWriteAgent 生命周期钩子 |
| `api/agent/tools/memory_utils.py` | MEMORY.md 发现辅助函数 |
| `api/agent/strategy/mem_recall_agent.py` | MemRecallAgent 类 |
| `api/agent/strategy/mem_write_agent.py` | MemWriteAgent 类 |
| `api/agent/strategy/main_agent_strategy.py` | 策略集成入口（修改） |
| `api/chat/session_event_streaming/event_types.py` | 事件类型扩展（修改） |
| [design 文档](./mem_maintainer_agents_spec_design.md) | 需求与设计规范 |
| [context 文档](./mem_maintainer_agents_spec_context.md) | 代码基础设施参考 |
