---
文档标题：mem_maintainer_agents_spec_design
文档描述：记忆维护Agent系统的需求与设计规范，包含概念设计、执行逻辑和文件结构
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [需求概述](#需求概述)
- [核心概念](#核心概念)
  - [记忆文件体系](#记忆文件体系)
  - [MemRecallAgent 与 MemWriteAgent 定位](#memrecallagent-与-memwriteagent-定位)
  - [Inject 钩子模式](#inject-钩子模式)
  - [Tool Steering 机制](#tool-steering-机制)
  - [XML 标记约定](#xml-标记约定)
- [执行逻辑](#执行逻辑)
  - [任务执行策略总览](#任务执行策略总览)
  - [记忆召回阶段](#记忆召回阶段)
  - [主 Agent 执行阶段](#主-agent-执行阶段)
  - [后台记忆修改阶段](#后台记忆修改阶段)
- [MemRecallAgent 实现细节](#memrecallagent-实现细节)
  - [类结构](#memrecallagent-类结构)
  - [return_memory_recall 闭包](#return_memory_recall-闭包)
  - [inject_memory_recall_context 钩子](#inject_memory_recall_context-钩子)
  - [inject_return_memory_recall_closure 钩子](#inject_return_memory_recall_closure-钩子)
- [MemWriteAgent 实现细节](#memwriteagent-实现细节)
  - [类结构](#memwriteagent-类结构)
  - [inject_memory_write_context 钩子](#inject_memory_write_context-钩子)
- [MEMORY.md 索引发现逻辑](#memorymd-索引发现逻辑)

---

## 需求概述

系统需要在每次用户交互时，自动召回并注入长期记忆上下文，并在交互完成后异步更新记忆文件。具体需求：

1. **记忆召回**：在主 Agent 执行前，根据当前会话上下文（项目路径、用户信息等）从文件系统中检索相关记忆，将结果注入主 Agent 的 `major` Marker。
2. **记忆写入**：在主 Agent 执行后，根据交互内容异步更新记忆文件（新增、修改、删除）。
3. **非阻塞设计**：记忆召回为同步前置步骤（可失败降级），记忆写入为异步后台步骤。

---

## 核心概念

### 记忆文件体系

记忆文件存储在 JuiceFS 分布式文件系统的 `/dist_fs/sys/memory/` 路径下，按作用域分三级：

| 作用域 | 路径模式 | 用途 |
|--------|---------|------|
| 全局记忆 | `/dist_fs/sys/memory/global` | 跨项目的用户偏好、通用知识 |
| 项目记忆 | `/dist_fs/sys/memory/projects/<project_path>` | 项目特定的约定、架构决策 |
| 外部交互记忆 | `/dist_fs/sys/memory/external_facing/<entity_identifier>` | 与外部实体的交互经验 |

每个记忆目录包含 `MEMORY.md` 索引文件和多个记忆 Markdown 文件。索引文件使用链接列表格式，每条记录包含文件名和一句话摘要：

```markdown
- [用户是高级后端工程师](user_role.md) — Go专家，React新手，用后端类比解释前端
- [测试必须用真实数据库](feedback_testing.md) — 不要 mock 数据库，曾因此出过生产事故
```

记忆文件使用 Frontmatter 元数据 + 正文 Markdown 格式，Frontmatter 包含 `name`、`description`、`type` 三个字段。`type` 取值为 `user`、`feedback`、`project`、`reference`、`knowledge` 之一。

### MemRecallAgent 与 MemWriteAgent 定位

两个 Agent 均为**实用类**，结构类似 `MainAgent`（参见 `api/agent/strategy/main_agent.py`），但有以下区别：

- 不使用 `StreamingProcessor`，无需向前端推送流式消息。
- 保留 `summarization_compact` 相关装饰器的一致性设计。
- 保留 `session_task` 的 property 属性。
- `on_tool_call_start` 保持当前实现（注入 user_id / session_id 元数据）。

**MemRecallAgent** 负责只读检索，拥有专属工具 `return_memory_recall`，将检索到的记忆内容推送到主 Agent 的指定 Marker。

**MemWriteAgent** 负责读写更新，使用标准文件系统工具和 Bash 工具完成记忆文件的增删改。

### Inject 钩子模式

两个 Agent 的上下文注入遵循 `summarization_compact` 的钩子模式（参见 `api/agent/tools/summarization_compact/lifecycle_hooks.py`），但使用的是**二钩子变体**（而非完整三钩子）：

1. **on_agent_start**：注入上下文消息到 MemoryTrails，包含工作要求、MEMORY.md 索引内容，以及 `GENERATION_TOOL_PARAM` 的工具参数定义（以 `TOOL_DISCOVERY_RESULT_BLOCK` 的形式提供给 LLM，而非通过 `prepare_tool_params` 注册到 `tools` 参数中）。
2. **prepare_tool_closures**（`modifies_return=True`）：动态构造工具闭包并注入到闭包集合。

> **注意**：MemRecallAgent / MemWriteAgent 不使用 `prepare_tool_params` 钩子。工具参数定义在 `on_agent_start` 的上下文消息中以 `TOOL_DISCOVERY_RESULT_BLOCK` 形式提供给 LLM，LLM 据此理解和调用工具，而非通过 OpenAI `tools` 参数注册。

### Tool Steering 机制

通过 `AgentBase._tool_choice_steering: set[str]`（参见 `api/agent/base_agent.py`）限制 Agent 可调用的工具子集。设置后，Agent 只能调用集合内的工具；若 Agent 以纯文本回复而非工具调用，系统会注入 steering 提示强制其使用工具。

### XML 标记约定

系统在 `api/agent/xml_marks_def.py` 中定义 XML 标记常量，用于在消息中划分结构化内容区域。本次需新增 `MEMORY_RECALL_BLOCK_START` / `MEMORY_RECALL_BLOCK_END` 标记，包裹记忆召回内容，使其在上下文中语义明确。

---

## 执行逻辑

### 任务执行策略总览

完整的任务执行分为三个阶段，修改现有的 `main_agent_strategy`（参见 `api/agent/strategy/main_agent_strategy.py`）：

```
main_agent_strategy()
  |
  +---> 阶段1：记忆召回（同步前置，条件执行）
  |       if should_recall:
  |         MemRecallAgent.run() → 结果注入 major Marker
  |
  +---> 阶段2：主 Agent 执行（无变化）
  |       MainAgent.run("major", service_name)
  |
  +---> 阶段3：后台记忆修改（asyncio Task，条件独立于阶段1）
          if should_write:  # 独立判断条件
            MemWriteAgent.run() → 异步，不阻塞返回
```

记忆召回和记忆写入的执行条件**相互独立**。记忆召回的判断条件在 `main_agent_strategy` 入口处决定（`should_recall`）；记忆写入阶段使用独立的判断条件（`should_write`），即使不召回记忆，主 Agent 执行后的交互内容仍可能需要写入记忆。若两个条件均不满足，则仅运行阶段2。

### 记忆召回阶段

1. 使用独立的 `logfire.span` 包裹整个召回过程。
2. 初始化 `MemRecallAgent`，**共享**主 Agent 的 `MemoryTrails` 实例。
3. 通过 `fork_marker("base", "mem_recall:<random_uuidv7>")` 创建召回专用 Marker，从 base Marker 分叉以共享历史上下文。
4. 设置只读 `tool_steering`（限定为文件读取类工具，如 Read、List）。
5. 在 `try/except` 块中执行 `agent.run()`，异常时向 `major` Marker 追加失败提示消息（不中断主流程）。
6. 执行前后通过 `publish_SSE_session_event` 发布会话事件。

### 主 Agent 执行阶段

与现有逻辑完全一致（参见 `api/agent/strategy/main_agent_strategy.py`）。召回阶段注入到 `major` Marker 的记忆内容已被包含在主 Agent 的上下文中。

### 后台记忆修改阶段

记忆写入阶段的执行条件**独立于召回阶段**——即使不召回记忆，主 Agent 执行后的交互内容仍可能需要写入记忆。写入阶段应在独立的判断条件下执行（或始终执行）。

1. 使用独立的 `logfire.span` 包裹。
2. 初始化 `MemWriteAgent`，同样共享 `MemoryTrails` 实例。
3. 通过 `fork_marker("base", "mem_write:<random_uuidv7>")` 创建写入专用 Marker。
4. 设置常用读写工具和 Bash 工具的 `tool_steering`。
5. 使用 `asyncio.create_task` 创建后台 Task 执行。
6. 执行前后通过 `publish_SSE_session_event` 发布会话事件。

---

## MemRecallAgent 实现细节

### MemRecallAgent 类结构

类定义位于 `api/agent/strategy/` 下，继承 `AgentBase`，核心属性与 `MainAgent` 对齐但省略 `StreamingProcessor`：

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
        ...

    # recommend_memory_recall_target_marker 属性
    # 可作为其他用途的配置参考，不作为 target_marker 的默认值回退
    @property
    def recommend_memory_recall_target_marker(self) -> str:
        return "major"
```

### return_memory_recall 闭包

闭包由 `inject_return_memory_recall_closure` 钩子在 `prepare_tool_closures` 阶段动态构造，捕获 `MemoryTrails` 实例和执行 Marker 名称。

**工具参数定义**（`GENERATION_TOOL_PARAM`）：

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `target_marker` | `str` | 否 | 目标 Marker 名称，默认 `"major"`（由 Pydantic Field 直接提供默认值） |
| `mem_files` | `list[str]` | 是 | 需要召回的记忆文件绝对路径列表 |
| `additional_msg` | `str | None` | 否 | 附加说明文本 |

**工具行为**：

1. 读取 `mem_files` 中每个文件的内容。
2. 使用 `<memory_recall>` XML 标记包裹所有文件内容，组装为一条系统消息。
3. 通过 `memory_trails.append_to_marker(target_marker, msg)` 推送到主 Agent 对应的 Marker。

闭包的关键结构（伪代码）：

```python
def make_return_memory_recall_closure(
    memory_trails: MemoryTrails,
    juicefs_backend: "JuiceFSBackend",
) -> ToolClosure:
    async def closure(**kwargs) -> ToolTaskResult:
        param = ReturnMemoryRecallParamDefine.model_validate(kwargs)
        target = param.target_marker

        # 通过 juicefs_backend.read_file() 读取文件、组装消息、推送到 target marker
        parts = []
        for file_path in param.mem_files:
            content, _, _ = await juicefs_backend.read_file(file_path)
            parts.append(f"### {file_path}\n{content}")
        ...
    return closure
```

### inject_memory_recall_context 钩子

此钩子在 `on_agent_start` 阶段注入，提供记忆召回所需上下文。注入内容包含三部分：

**第一部分：记忆召回工作要求**（简短的系统提示，指导 Agent 如何执行记忆召回）。

**第二部分：相关 MEMORY.md 索引文件**。发现逻辑为：
1. 从 `tool_init_res.allowed_rel_dirs_in_juicefs_for_tool` 获取相对路径集合。
2. 将相对路径转为 `/dist_fs` 开头的绝对路径。
3. 检查这些路径是否落在 `/dist_fs/sys/memory/` 子路径下。
4. 对命中的子路径，通过 `discover_memory_index_files` 函数（内部自行获取 `JuiceFSSdkBackend` 实例）查询其下是否存在 `MEMORY.md` 文件。
5. 将找到的 `MEMORY.md` 内容注入上下文。

**第三部分：工具参数披露与限制**。包含 `return_memory_recall` 的 `GENERATION_TOOL_PARAM` 定义（渲染为 JSON 供 LLM 理解），以及通过 `tool_steering` 限制 Agent 只能使用只读工具 + `return_memory_recall`。

### inject_return_memory_recall_closure 钩子

此钩子在 `prepare_tool_closures` 阶段执行（`modifies_return=True`），调用 `make_return_memory_recall_closure` 构造闭包并注入到闭包字典中。结构与 `inject_summarization_compact_closure`（参见 `api/agent/tools/summarization_compact/lifecycle_hooks.py`）一致。

---

## MemWriteAgent 实现细节

### MemWriteAgent 类结构

与 `MemRecallAgent` 基本一致，但不需要专属工具闭包（使用标准文件系统工具和 Bash 工具）：

```python
@agent_decorator(inject_memory_write_context)
class MemWriteAgent(AgentBase):
    def __init__(self, user_id, session_id, session_task_id,
                 cancel_event, tool_init_res, **kwargs):
        super().__init__(cancel_event, tool_init_res)
        ...
```

### inject_memory_write_context 钩子

此钩子在 `on_agent_start` 阶段注入，内容包含：

**第一部分：记忆写入工作要求**（简短的系统提示，说明需要根据交互内容判断是否更新记忆文件，以及如何更新）。

**第二部分：相关 MEMORY.md 索引文件**。使用与 `inject_memory_recall_context` 相同的 `discover_memory_index_files` 函数（传入 `tool_init_res`），将找到的 `MEMORY.md` 内容注入上下文。

**第三部分：工具限制**。通过 `tool_steering` 设置允许的读写工具和 Bash 工具。

---

## MEMORY.md 索引发现逻辑

两个 Agent 的 context 注入均需要发现和读取 `MEMORY.md` 文件。统一逻辑如下：

```python
async def discover_memory_index_files(
    allowed_rel_dirs: set[PurePosixPath],
    tool_init_res: "ToolInitializationResult",
) -> list[str]:
    """
    从允许的相对路径集合中，发现 /dist_fs/sys/memory/ 子路径下的 MEMORY.md。

    内部通过 tool_init_res 自行获取 JuiceFSSdkBackend 实例。

    Returns:
        MEMORY.md 文件的内容列表
    """
    memory_root = PurePosixPath("/dist_fs/sys/memory")
    backend = _get_juicefs_backend(tool_init_res)
    found = []
    for rel_dir in allowed_rel_dirs:
        abs_path = PurePosixPath("/dist_fs") / rel_dir
        # 检查 abs_path 是否在 memory_root 下
        try:
            abs_path.relative_to(memory_root)
        except ValueError:
            continue
        memory_md_path = abs_path / "MEMORY.md"
        if await backend.file_exists(str(memory_md_path)):
            content, _, _ = await backend.read_file(str(memory_md_path))
            found.append(content)
    return found
```

此函数需要结合 `JuiceFSSdkBackend` 的路径校验机制（参见 `api/agent/tools/file_operations/storage_backend/juicefs_sdk.py` 的 `_check_work_dir_access` 方法），确保只访问授权范围内的路径。

---

## 新增 XML 标记

在 `api/agent/xml_marks_def.py` 中新增：

```python
MEMORY_RECALL_BLOCK_START = "<memory_recall>"
MEMORY_RECALL_BLOCK_END = "</memory_recall>"
```

用于 `return_memory_recall` 闭包组装消息时包裹记忆文件内容。

---

## Session Event 扩展

在 `api/chat/session_event_streaming/event_types.py` 的 `SessionEventType` 中新增两个事件类型：

| 事件类型 | 用途 |
|----------|------|
| `mem_recall_started` | 记忆召回开始 |
| `mem_recall_completed` | 记忆召回完成 |
| `mem_write_started` | 记忆写入开始 |
| `mem_write_completed` | 记忆写入完成 |

对应的事件载荷类需包含 `session_task_id` 字段，便于前端展示记忆维护的进度状态。

---

## 相关文件索引

| 文件 | 角色 |
|------|------|
| `api/agent/base_agent.py` | AgentBase 基类，提供核心循环和生命周期方法 |
| `api/agent/strategy/main_agent.py` | MainAgent 实现 |
| `api/agent/strategy/main_agent_strategy.py` | 主策略入口，需修改以集成记忆维护 |
| `api/agent/memory_trails/trails.py` | MemoryTrails，提供 Marker 操作 |
| `api/agent/tools/summarization_compact/lifecycle_hooks.py` | 三钩子模式的参考实现 |
| `api/agent/tools/summarization_compact/tool_closure.py` | 闭包构造的参考实现 |
| `api/agent/tools/summarization_compact/config_data_model.py` | 工具参数定义的参考实现 |
| `api/agent/xml_marks_def.py` | XML 标记常量定义 |
| `api/agent/tools/file_operations/storage_backend/juicefs_sdk.py` | JuiceFS 文件操作后端 |
| `api/chat/data_model.py` | ToolInitializationResult 定义 |
| `api/chat/session_event_streaming/event_types.py` | Session 事件类型定义 |
| `api/chat/session_event_streaming/publisher.py` | Session 事件发布 |
| `api/agent/life_cycle_decorators/__init__.py` | agent_decorator 和 lifecycle_hook |
