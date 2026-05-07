---
文档标题：mem_maintainer_agents_spec_todo
文档描述：记忆维护Agent系统的开发待办事项列表
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [Phase 1: 基础设施](#phase-1-基础设施)
  - [新增 XML 标记常量](#新增-xml-标记常量)
  - [Session Event 类型扩展](#session-event-类型扩展)
  - [MEMORY.md 发现辅助函数](#memorymd-发现辅助函数)
- [Phase 2: MemRecallAgent](#phase-2-memrecallagent)
  - [return_memory_recall 工具参数定义](#return_memory_recall-工具参数定义)
  - [return_memory_recall 工具闭包](#return_memory_recall-工具闭包)
  - [inject_memory_recall_context 装饰器](#inject_memory_recall_context-装饰器)
  - [inject_return_memory_recall_closure 装饰器](#inject_return_memory_recall_closure-装饰器)
  - [MemRecallAgent 类](#memrecallagent-类)
- [Phase 3: MemWriteAgent](#phase-3-memwriteagent)
  - [inject_memory_write_context 装饰器](#inject_memory_write_context-装饰器)
  - [MemWriteAgent 类](#memwriteagent-类)
- [Phase 4: 集成](#phase-4-集成)
  - [修改 main_agent_strategy](#修改-main_agent_strategy)
  - [记忆召回判断逻辑](#记忆召回判断逻辑)
  - [后台写入任务](#后台写入任务)
- [Phase 5: 测试](#phase-5-测试)
  - [单元测试](#单元测试)
  - [集成测试](#集成测试)

---

## Phase 1: 基础设施

本阶段完成所有前置依赖项，为后续 Agent 开发提供基础能力。设计细节参见 [设计文档 - XML 标记约定](./mem_maintainer_agents_spec_design.md#xml-标记约定) 与 [设计文档 - Session Event 扩展](./mem_maintainer_agents_spec_design.md#session-event-扩展)。

### 新增 XML 标记常量

- [ ] **文件**：`api/agent/xml_marks_def.py`
- [ ] 新增 `MEMORY_RECALL_BLOCK_START = "<memory_recall>"`
- [ ] 新增 `MEMORY_RECALL_BLOCK_END = "</memory_recall>"`
- [ ] 验证常量命名与现有标记常量风格一致（参考 `TODO_LIST_BLOCK_START/END` 等）

### Session Event 类型扩展

- [ ] **文件**：`api/chat/session_event_streaming/event_types.py`
- [ ] 在 `SessionEventType` 中新增以下四个事件类型：
  - `mem_recall_started`
  - `mem_recall_completed`
  - `mem_write_started`
  - `mem_write_completed`
- [ ] 新增对应的事件载荷类，包含 `session_task_id` 字段
- [ ] 验证新事件类型不与现有类型（`heartbeat`, `branch_task_started`, `branch_task_completed`）冲突
- [ ] 参考现有事件发送接口 `api/chat/session_event_streaming/publisher.py`，确认新事件可正常发布

### MEMORY.md 发现辅助函数

- [ ] **文件**：建议放置于 `api/agent/tools/` 下的新建子模块（如 `api/agent/tools/memory_utils/`）
- [ ] 实现 `discover_memory_index_files(allowed_rel_dirs, tool_init_res)` 异步函数
- [ ] 函数逻辑：
  1. 遍历 `allowed_rel_dirs: set[PurePosixPath]`
  2. 将每个相对路径转为 `/dist_fs` 开头的绝对路径
  3. 检查绝对路径是否落在 `/dist_fs/sys/memory/` 子路径下（使用 `PurePosixPath.relative_to` 判断）
  4. 对命中的子路径，通过 `juicefs_backend.file_exists` 检查 `MEMORY.md` 是否存在
  5. 存在则通过 `juicefs_backend.read_file` 读取内容并收集
  6. 返回所有 `MEMORY.md` 文件的内容列表
- [ ] 验证路径校验逻辑与 `JuiceFSSdkBackend._check_work_dir_access`（参见 `api/agent/tools/file_operations/storage_backend/juicefs_sdk.py`）一致
- [ ] 编写函数的单元测试（参见 [Review 文档 - MEMORY.md 发现逻辑测试](./mem_maintainer_agents_spec_review.md#memorymd-发现逻辑测试)）

---

## Phase 2: MemRecallAgent

本阶段实现记忆召回 Agent 的全部组件。设计细节参见 [设计文档 - MemRecallAgent 实现细节](./mem_maintainer_agents_spec_design.md#memrecallagent-实现细节)。

### return_memory_recall 工具参数定义

- [ ] **文件**：`api/agent/tools/` 下新建 `memory_recall/` 工具目录
- [ ] 创建 `config_data_model.py`，定义 `ReturnMemoryRecallParamDefine` Pydantic 模型：
  - `target_marker: str = Field(default="major", ...)` — 目标 Marker 名称，默认 `"major"`
  - `mem_files: list[str]` — 必填，记忆文件绝对路径列表
  - `additional_msg: str | None = None` — 附加说明文本
- [ ] 定义 `GENERATION_TOOL_PARAM: ChatCompletionToolParam` 常量，JSON Schema 与上述参数定义一致
- [ ] 参考现有工具的参数定义模式（参见 `api/agent/tools/summarization_compact/config_data_model.py`）

### return_memory_recall 工具闭包

- [ ] **文件**：`api/agent/tools/memory_recall/tool_closure.py`
- [ ] 实现 `make_return_memory_recall_closure(memory_trails, juicefs_backend)` 函数：
  1. 接收 `MemoryTrails` 实例和 `JuiceFSBackend` 实例
  2. 返回 `ToolClosure` 类型的异步闭包
  3. 闭包内部：
     - 使用 `ReturnMemoryRecallParamDefine.model_validate(kwargs)` 解析参数
     - `target_marker` 默认为 `"major"`（由 Pydantic Field 直接提供）
     - 逐个通过 `juicefs_backend.read_file` 读取 `mem_files` 中的文件内容
     - 使用 `MEMORY_RECALL_BLOCK_START/END` XML 标记包裹所有内容
     - 如果有 `additional_msg`，附加到消息开头
     - 通过 `memory_trails.append_to_marker(target, msg, is_new=True, to_agent_msg=True)` 推送
     - 返回 `ToolTaskResult(str_content="...")`
  4. 文件读取失败时返回 `ToolTaskResult(str_content="错误信息", occur_error=True)`
- [ ] 闭包签名与 `ToolClosure` 类型（`Callable[..., Coroutine[Any, Any, ToolTaskResult]]`）兼容
- [ ] 参考现有闭包构造模式（参见 `api/agent/tools/summarization_compact/tool_closure.py`）

### inject_memory_recall_context 装饰器

- [ ] **文件**：`api/agent/tools/memory_recall/lifecycle_hooks.py`
- [ ] 实现 `inject_memory_recall_context` 钩子：
  - 装饰为 `@lifecycle_hook("on_agent_start", position="after")`
  - 注入内容包括三部分：
    1. **记忆召回工作要求**：简短系统提示，指导 Agent 执行记忆召回
    2. **MEMORY.md 索引文件**：调用 `discover_memory_index_files` 获取内容并注入
    3. **工具参数披露与限制**：将 `GENERATION_TOOL_PARAM` 以 `TOOL_DISCOVERY_RESULT_BLOCK` 包裹后注入上下文，设置 `tool_steering`
  - 设置 `tool_steering` 为只读工具集合（`read_file`, `list_directory`, `get_item_type`）+ `return_memory_recall`
- [ ] 验证 `tool_init_res.allowed_rel_dirs_in_juicefs_for_tool` 的访问方式正确（参见 `api/chat/data_model.py` 的 `ToolInitializationResult` 定义）

### inject_return_memory_recall_closure 装饰器

- [ ] **文件**：`api/agent/tools/memory_recall/lifecycle_hooks.py`（同上）
- [ ] 实现 `inject_return_memory_recall_closure` 钩子：
  - 装饰为 `@lifecycle_hook("prepare_tool_closures", position="after", modifies_return=True)`
  - 在原方法返回的 closures 字典中注入 `return_memory_recall` 键
  - 调用 `make_return_memory_recall_closure(memory_trails, juicefs_backend)` 构造闭包
  - 返回修改后的 closures 字典
- [ ] 参考模式与 `inject_summarization_compact_closure`（参见 `api/agent/tools/summarization_compact/lifecycle_hooks.py`）一致

### MemRecallAgent 类

- [ ] **文件**：`api/agent/strategy/` 下新建 `mem_recall_agent.py`
- [ ] 类定义：
  - 继承 `AgentBase`
  - 使用 `@agent_decorator(inject_memory_recall_context, inject_return_memory_recall_closure)` 注册钩子
  - 构造参数：`user_id`, `session_id`, `session_task_id`, `cancel_event`, `tool_init_res`, `**kwargs`
  - 调用 `super().__init__(cancel_event, tool_init_res)`
- [ ] `session_task` 属性：使用 `@property` + `async def` 实现懒加载（与 `MainAgent` 模式一致）
- [ ] `recommend_memory_recall_target_marker` 属性：
  - `@property` 装饰
  - 默认返回 `"major"`
- [ ] 不包含 `StreamingProcessor`（与 `MainAgent` 的区别）
- [ ] 参考设计文档中的 [类结构定义](./mem_maintainer_agents_spec_design.md#memrecallagent-类结构)

---

## Phase 3: MemWriteAgent

本阶段实现记忆写入 Agent。设计细节参见 [设计文档 - MemWriteAgent 实现细节](./mem_maintainer_agents_spec_design.md#memwriteagent-实现细节)。

### inject_memory_write_context 装饰器

- [ ] **文件**：建议放置于 `api/agent/tools/` 下的新建子模块（如 `api/agent/tools/memory_write/`）的 `lifecycle_hooks.py`
- [ ] 实现 `inject_memory_write_context` 钩子：
  - 装饰为 `@lifecycle_hook("on_agent_start", position="after")`
  - 注入内容包括三部分：
    1. **记忆写入工作要求**：简短系统提示，说明根据交互内容判断是否更新记忆文件及如何更新
    2. **MEMORY.md 索引文件**：调用 `discover_memory_index_files` 获取内容并注入
    3. **工具限制**：设置 `tool_steering` 为读写工具 + Bash 工具（`read_file`, `write_file`, `list_directory`, `get_item_type`, `bash`）

### MemWriteAgent 类

- [ ] **文件**：`api/agent/strategy/` 下新建 `mem_write_agent.py`
- [ ] 类定义：
  - 继承 `AgentBase`
  - 使用 `@agent_decorator(inject_memory_write_context)` 注册钩子
  - 构造参数：`user_id`, `session_id`, `session_task_id`, `cancel_event`, `tool_init_res`, `**kwargs`
  - 调用 `super().__init__(cancel_event, tool_init_res)`
- [ ] `session_task` 属性：与 `MemRecallAgent` 相同的懒加载实现
- [ ] 不包含自定义工具闭包（使用标准文件系统工具和 Bash 工具）
- [ ] `on_tool_call_start` 保持当前实现（注入 `user_id` / `session_id` 元数据）
- [ ] 参考设计文档中的 [类结构定义](./mem_maintainer_agents_spec_design.md#memwriteagent-类结构)

---

## Phase 4: 集成

本阶段修改现有策略入口，将记忆维护 Agent 集成到主执行流程中。设计细节参见 [设计文档 - 执行逻辑](./mem_maintainer_agents_spec_design.md#执行逻辑)。

### 修改 main_agent_strategy

- [ ] **文件**：`api/agent/strategy/main_agent_strategy.py`
- [ ] 将现有的单阶段执行改为三阶段：
  1. **阶段1 - 记忆召回**：同步前置
  2. **阶段2 - 主 Agent 执行**：与现有逻辑一致
  3. **阶段3 - 后台记忆修改**：异步非阻塞
- [ ] 在策略入口处添加记忆召回判断逻辑（条件判断是否执行阶段1），以及独立的记忆写入判断逻辑（条件判断是否执行阶段3）
- [ ] 确保 `MemoryTrails` 实例在三个阶段间正确共享

### 记忆召回判断逻辑

- [ ] 在 `main_agent_strategy` 入口处实现判断条件
- [ ] 召回判断逻辑依据：
  - 检查 `tool_init_res.allowed_rel_dirs_in_juicefs_for_tool` 是否包含 memory 相关路径
  - 若包含，则执行阶段1；否则跳过
- [ ] 写入判断逻辑（独立于召回判断）：
  - 使用独立的 `should_write` 条件，即使不召回记忆，交互内容仍可能需要写入记忆
  - 写入阶段条件独立于召回阶段条件
- [ ] 判断结果不影响阶段2（主 Agent 执行）的正常运行

### 后台写入任务

- [ ] 使用 `asyncio.create_task` 创建后台 Task 执行 MemWriteAgent
- [ ] 在 Task 启动前发送 `mem_write_started` 事件
- [ ] 在 Task 完成后发送 `mem_write_completed` 事件（使用 `task.add_done_callback` 或在协程内部处理）
- [ ] 确保后台任务的异常被静默捕获并记录（logfire），不影响主流程返回
- [ ] 使用独立的 `logfire.span` 包裹后台任务执行

---

## Phase 5: 测试

本阶段编写和执行全部测试用例。测试设计参见 [Review 文档 - 测试建议](./mem_maintainer_agents_spec_review.md#测试建议)。

### 单元测试

- [ ] **MEMORY.md 发现逻辑测试**
  - 正常发现：有效路径下存在 `MEMORY.md`
  - 路径不在 memory_root 下：不应被收录
  - 路径下无 `MEMORY.md`：返回空列表
  - 空输入集合：返回空列表
  - 多个有效路径：全部返回
- [ ] **工具闭包参数验证测试**
  - 合法参数解析正确
  - `target_marker` 默认值回退
  - 缺少必填参数校验
- [ ] **XML 标记包裹测试**
  - 标记常量值正确
  - 单文件内容包裹
  - 多文件内容包裹
- [ ] **Session Event 类型测试**
  - 四种新事件类型正确注册
  - 事件载荷序列化正确

### 集成测试

- [ ] **完整召回流程测试**
  - 从策略入口触发 MemRecallAgent
  - 验证 Marker 分叉、MEMORY.md 注入、工具调用、内容推送
  - 验证召回结果在 major Marker 中可见
- [ ] **完整写入流程测试**
  - 主 Agent 执行后触发 MemWriteAgent
  - 验证异步非阻塞行为
  - 验证工具限制生效
- [ ] **Marker 分叉隔离测试**
  - mem_recall Marker 操作不影响 major Marker
  - mem_write Marker 操作不影响 major Marker
  - 两个分支之间无交叉
- [ ] **异常处理测试**
  - 召回异常不阻塞主 Agent
  - 写入异常静默处理
  - 取消事件响应
