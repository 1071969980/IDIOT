# API 上下文

IDIOT API 的核心领域——AI 代理会话系统。用户与 AI 代理的对话被建模为可分支、可回溯的会话结构，类似 Git 版本控制模型。

## 语言

### 核心实体

**会话 (Session)**：
用户与 AI 代理之间的一次持续对话容器。一个会话可包含多个分支，每条分支代表一条独立的对话演进路径。会话由 user、agent 或 system 创建，拥有独立的代理配置。
_Avoid_: 对话、聊天室、项目
_Key file_: `api/chat/sql_stat/u2a_session/utils.py`

**会话分支 (Session Branch)**：
会话内的一条独立对话演进路径。分支本身是一个命名指针，指向其任务链的末端（叶子任务）。同一会话下可有多个分支并行存在，默认分支名为 `main`。
_Avoid_: 对话线程、对话链、分叉
_Key file_: `api/chat/sql_stat/u2a_session_branch/utils.py`

**会话任务 (Session Task)**：
会话内一次 AI 处理的基本工作单元。任务以树状结构组织，每个任务记录其父任务和物化路径（`ltree`）。任务有明确的生命周期状态（`pending` → `processing` → `completed`/`failed`/`cancelled`），并携带会话分支状态和上下文断点。
_Avoid_: 作业、请求、回合
_Key file_: `api/chat/sql_stat/u2a_session_task/utils.py`

### 身份与权限

**身份验证 (Authentication)**：
基于 JWT 的用户身份认证体系。用户通过用户名和密码注册、登录，获取签发的 JWT token——支持短期 token（15 分钟）和"记住我"长期 token（默认 30 天）。后续请求通过 Bearer header 或 cookie 携带 token 验证身份。提供 token 刷新和登出机制。
_Avoid_: 登录、鉴权、授权
_Key file_: `api/authentication/`

### 消息

**会话用户消息 (Session User Message)**：
用户在会话中发送给 AI 代理的消息。每条消息归属于一个会话任务，在会话内拥有全局递增序号，处理过程中经历 `waiting_agent_ack_user` → `agent_working_for_user` → `completed`/`error` 的状态流转。
_Avoid_: 用户输入、提问、对话记录
_Key file_: `api/chat/sql_stat/u2a_user_msg/utils.py`

**会话代理消息 (Session Agent Message)**：
AI 代理在会话中返回给用户的回复。消息类型包括文本（`text`）、工具调用（`tool_call`）、会话链接（`u2a_session_link`、`a2a_session_link`）。状态流转为 `streaming` → `stop` → `completed`/`error`。每条消息归属于一个会话任务，在任务内拥有自增子序号。
_Avoid_: AI回复、机器人消息、助手消息
_Key file_: `api/chat/sql_stat/u2a_agent_msg/utils.py`

### 配置

**会话配置 (Session Config)**：
定义 AI 代理在会话中行为方式的配置，包括系统提示、启用的工具集、MCP 连接。配置采用两层合并机制：会话级基础配置 + 任务级覆写（通过会话分支状态叠加），合并后形成有效配置。配置带语义化版本号，处理时校验主版本兼容性。
_Avoid_: Agent设置、机器人配置
_Key file_: `api/agent/session_agent_config/config_data_model.py`

**会话元数据 (Session Metadata)**：
会话自身的属性信息，包括标题（`title`）、归档状态（`archived`）、上下文锁定（`context_lock`）、创建者角色（`created_by`）等。与会话配置（代理行为配置）是两个独立概念。
_Avoid_: 会话属性、会话信息
_Key file_: `api/chat/sql_stat/u2a_session/utils.py`

**系统提示 (System Prompt)**：
发送给 AI 模型的基础指令文本，定义代理的角色、行为边界和任务规则。支持五种来源组合：纯文本、变量引用、LangFuse 远程模板、Jinja 文件模板、Jinja 字符串模板。通过渲染引擎合并后注入模型上下文。
_Avoid_: 提示词、系统指令、角色设定
_Key file_: `api/chat/render_system_prompt.py`

**会话配置命令 (Session Configuration Command)**：
通过命令模式在运行时修改会话代理配置的接口。支持的命令包括：查询/修改工具启用状态与可见性、读写 MCP 服务器配置、测试 MCP 连接。命令执行受分布式锁保护，异常时自动回滚，确保并发安全与配置一致性。
_Avoid_: 配置接口、设置 API
_Key file_: `api/app/chat/session_agent_config/`

### 状态

**会话分支状态 (Session Branch State)**：
会话任务携带的 JSON 状态容器，包含配置覆写、已加载技能、待办事项等运行时数据。状态沿分支路径自动继承（新任务从最近祖先复制），仅在 `pending` 状态可写，支持分支路径上的状态回溯与任务级隔离。
_Avoid_: 存储快照、任务数据、上下文
_Key file_: `api/chat/sql_stat/u2a_session_branch_task/storage_snapshot_keys.py`

**会话全局状态 (Session Global State)**：
会话级别的 JSON 状态容器，每会话仅一条记录，跨所有分支共享。修改对所有分支立即可见，读写操作受 Redis 分布式锁保护。用于存储跨分支的临时状态和变量。
_Avoid_: 会话存储、共享数据
_Key file_: `api/agent/sql_stat/u2a_session_storage/utils.py`

### 上下文管理

**会话上下文断点 (Session Context Breakpoint)**：
会话任务上标记的消息序号数组，定义上下文窗口的截断边界。当沿分支路径回溯构建上下文时，遇到断点即停止——断点之前的对话历史不会被纳入模型上下文。
_Avoid_: 截断点、分割点、历史边界
_Key file_: `api/chat/sql_stat/u2a_session_task/utils.py`

**上下文压缩 (Context Compaction)**：
LLM 在对话上下文接近容量上限时主动执行的总结压缩机制。系统监测 token 用量，达到阈值时引导模型调用压缩工具——模型自行撰写历史总结，该总结作为上下文断点写入记忆轨迹，使得后续 LLM 请求仅发送断点之后的内容。压缩完成后自动恢复工具启用状态、TODO 列表、已加载技能等运行时状态，确保任务连续性。
_Avoid_: 摘要、总结、截断
_Key file_: `api/agent/tools/summarization_compact/`

**子代理 (Sub-Agent)**：
主代理通过工具委派任务而创建的独立代理实例。每个子代理在独立分支中运行，仅可使用其定义文件声明的工具集。支持两种上下文模式：`standalone`（空白上下文，从零开始）和 `fork`（继承主代理当前对话上下文）。子代理完成后通过系统通知告知主代理结果。
_Avoid_: 子任务、worker、子进程
_Key file_: `api/agent/tools/sub_agent/`

**分支间消息 (Inter-Branch Message)**：
同一会话内不同分支之间传递消息的通信机制。通过 `feed_message` 工具实现，支持按分支名或子代理别名路由消息，可控制是否触发目标分支立即处理。子代理通过此机制向主代理反馈进度与结果，主代理也可向子代理发送后续指令。
_Avoid_: 跨分支通信、消息传递
_Key file_: `api/agent/tools/feed_message/`

**系统提醒 (System Reminder)**：
代理启动或迭代时，根据运行时状态变化条件注入到 LLM 上下文的系统消息。以 `<system_reminder>` 包裹，用于告知模型当前会话中已发生的突发变化——如工具启用状态变更、分支切换、文件被外部修改、子代理完成等。与系统提示不同，系统提醒是瞬态且条件性的，仅在状态变化时注入，不参与定义代理的基础身份和行为规则。
_Avoid_: 系统通知、状态提示、运行时消息
_Key file_: `api/agent/system_reminder/`

### 人工介入

**人工介入 (Human in the Loop)**：
代理执行过程中主动暂停并向用户提问、等待用户响应的交互机制。代理通过工具向用户发送问题及预设选项，执行流通过 Redis Stream 双向通信阻塞等待，直至用户选择或输入自由文本后继续执行。与此相对，系统也支持异步通知模式——代理向用户发送信息但不等待回复。
_Avoid_: 人机交互、人工确认、用户审批
_Key file_: `api/human_in_loop/`

### 代理与执行

**代理 (Agent)**：
执行 AI 对话任务的核心组件。每个代理实例封装了 LLM 调用循环、工具执行和生命周期管理，持有独立的可用工具集、取消信号和运行时记忆。
_Avoid_: Bot、机器人、AI实例
_Key file_: `api/agent/base_agent.py`

**代理生命周期 (Agent Lifecycle)**：
代理从启动到结束经历的结构化执行阶段。包括：代理启动 → 循环迭代（迭代开始 → 内容生成 → 可选工具调用 → 迭代结束）→ 代理完成/取消。每个阶段节点支持通过钩子注入扩展逻辑。
_Avoid_: 执行流程、运行阶段
_Key file_: `api/agent/base_agent.py`

**代理生命周期钩子 (Agent Lifecycle Hook)**：
拦截代理生命周期节点的扩展函数。通过 `agent_decorator` 装饰器组合模式将多个横切关注点叠加到代理类上，替代多重继承。
_Avoid_: 回调、中间件、拦截器
_Key file_: `api/agent/life_cycle_decorators/composer.py`

**代理循环 (Agent Loop)**：
代理的核心执行流程。每次迭代调用 LLM 生成响应——若模型返回工具调用则执行工具并继续循环，若返回停止则结束。
_Key file_: `api/agent/base_agent.py`

**临时记忆轨迹 (Temporary Memory Trails)**：
代理运行时的内存树结构，用于组织和追踪对话过程中的消息片段。支持标记分叉以隔离不同处理阶段，最终从指定标记提取线性化记忆或持久化数据。
_Avoid_: 消息树、对话树、记忆链
_Key file_: `api/agent/memory_trails.py`

### 基础设施

**用户容器 (User Pod)**：
每个用户在 K8S 集群中分配的专属容器化运行环境。AI 代理通过 Bash 工具在此容器中执行命令。容器按需自动拉起（首次 Bash 调用时触发），通过心跳保持活跃，空闲超时或会话结束后自动释放。
_Avoid_: 沙箱、虚拟机、执行环境
_Key file_: `api/user_pod_scheduler/scheduler.py`

**用户文件系统 (User Filesystem)**：
每个用户独立的分布式文件系统，基于 JuiceFS 实现，挂载在用户容器的 `/dist_fs` 路径下。资源与用户一一对应，用户间完全隔离。供两条通道使用：AI 代理通过文件操作工具间接操作，或用户/应用通过 `user_file_system` HTTP API 直接上传下载及管理文件。默认提供 `sys`（系统）、`pub`（公共）、`priv`（私有）三个目录。
_Avoid_: 存储卷、云盘、工作目录
_Key file_: `api/agent/tools/file_operations/storage_backend/juicefs_sdk.py`、`api/app/user_file_system/`

### 工具系统

**工具 (Tool)**：
AI 代理可调用的函数单元。每个工具有两个面：面向 LLM 的 JSON Schema 参数定义（`ChatCompletionToolParam`），和面向运行时的可执行闭包（`ToolClosure`）。工具由 ToolFactory 根据会话配置中的 `tools_config` 统一实例化，注册到代理的可用工具集。
_Avoid_: 函数、插件、能力
_Key file_: `api/agent/tools/tool_factory/tool_factory.py`

**工具作用域 (Tool Scope)**：
参数化工具运行时行为的上下文信息。例如 Bash 工具通过作用域确定目标用户容器，文件操作工具据此确定可访问目录白名单和权限角色。作用域值从 `scope_def` 字典中按优先级路径解析（`resolve_scope_value()`），支持嵌套点号路径和回退查找。
_Avoid_: 工具参数、运行时配置
_Key file_: `api/agent/session_agent_config/utils.py`

**显式工具 / 隐式工具 (Explicit / Implicit Tool)**：
工具在 LLM 上下文中的可见性分类。显式工具直接注入模型上下文（Function Calling 列表中可见）；隐式工具已初始化但不在默认上下文中展示——模型需通过工具发现（Tool Discovery）来搜索和揭示它们。此机制在保留大量可用工具的同时节省上下文窗口。
_Avoid_: 可见工具/隐藏工具、主动工具/被动工具
_Key file_: `api/chat/tool_init.py`

**工具发现 (Tool Discovery)**：
一种特殊的元工具，允许模型在运行时搜索和获取隐式工具的完整定义。支持三种模式：BM25 语义搜索（按自然语言描述匹配）、正则匹配（按名称/描述 grep）、直接揭示（按名称获取完整 JSON Schema）。模型先搜索找到所需工具，再揭示其定义后调用。
_Avoid_: 工具搜索、工具检索
_Key file_: `api/agent/tools/tool_discovery/consturctor.py`

**MCP 工具 (MCP Tool)**：
通过 Model Context Protocol 从外部服务器动态加载的工具。`McpToolsLoader` 连接远程 MCP Server，将其工具包装为与内置工具一致的闭包格式，支持白名单/黑名单过滤、工具名加服务器前缀以避免冲突。加载后合并进代理的可用工具集。
_Avoid_: 远程工具、外部工具、插件工具
_Key file_: `api/agent/tools/mcp/adapter.py`

### 工具调用

**工具调用 (Tool Call)**：
代理循环中解析并执行模型工具调用的阶段。工具按执行策略分为顺序区（逐个执行）和并发区（并行执行），同一文件的多重编辑通过集结门协调。执行结果写回临时记忆轨迹。
_Key file_: `api/agent/base_agent.py`

**工具选择引导 (Tool Choice Steering)**：
限制代理当前可用工具集合的运行时机制。设置白名单后，非名单内的工具不可被调用；若阻止提前结束，模型在未调用工具前不得终止循环。
_Avoid_: 工具限制、工具过滤
_Key file_: `api/agent/base_agent.py`

### 事件与流

**会话任务消息流 (Session Task Message Stream)**：
单个会话任务内 AI 代理响应的实时 SSE 推送流。逐 token 输出文本生成、工具调用请求及执行结果，前端通过此流展示 AI 的实时回复过程。支持 `Last-Event-ID` 断线重连。
_Avoid_: 聊天流、响应流、token 流
_Key file_: `api/app/chat/listen_to_session_streaming.py`

**会话事件流 (Session Event Stream)**：
会话级生命周期事件的实时 SSE 推送流。覆盖范围大于单次任务——推送任务状态变更、分支变化、配置更新等会话全局事件。含 15 秒心跳保活和断线重连。
_Avoid_: 会话通知、系统事件
_Key file_: `api/app/chat/session_event_streaming/`

**HIL 事件流 (HIL Event Stream)**：
人工介入场景中代理向用户推送中断请求和通知的 SSE 流。前端通过此流接收用户选择表单和异步通知，用户响应通过 HTTP POST 回传。
_Avoid_: HIL 消息通道、人工交互流
_Key file_: `api/human_in_loop/http_worker/router.py`
