# 各工具对取消事件的响应实现情况 —— 系统调查报告

> 分析日期：2025-06-25（更新于 2026-06-26）  
> 分析范围：`api/agent/tools/` 下全部 13 个工具目录  
> 关联报告：[[cancel_signal_analysis_调查报告]]

---

## 一、核心结论

**13 个工具中，5 组（Bash、MCP、AskUser、FileOperations×7、SummarizationCompact）已实现 cancel_event 检查，剩余多数工具仍不检查。** 已修复工具均遵循统一模式：入口 `cancel_event.is_set()` fast-return + 下游透传 / `asyncio.wait` 竞态取消。SummarizationCompact 额外引入 savepoint/rollback 机制确保取消时完整恢复 memory_trails 状态。但 SubAgent、Skills、Todo、FeedMessage 等工具仍不响应取消信号，Memory/Recall、ToolDiscovery 因 Pydantic `extra='ignore'` 默认行为仍无法访问 cancel_event。

---

## 二、cancel_event 的传递机制

`base_agent.py` 的 `_execute_tool_calls` 方法（第 210-239 行）调用每个工具闭包时统一注入 `cancel_event`：

```python
# base_agent.py:214-219
data["task"] = asyncio.create_task(
    data["function"](
        exec_uuid=uuid,
        cancel_event=self.cancel_event,   # 统一注入
        **data["param"],
    ),
)
```

`cancel_event` 能否在工具内部被访问，取决于工具的 **Pydantic 参数模型配置** 和 **函数签名**：

| 接收模式 | 工具数 | 说明 |
|---------|--------|------|
| 通过 `**kwargs` + `extra='allow'` 进入 `model_extra`，已被提取并使用 | 4 组 | Bash、FileOperations(×7)、AskUser 均通过 `cast()` 提取并使用 |
| 通过 `**kwargs` + `extra='allow'` 进入 `model_extra`，未被提取 | 4 | Skills(×2)、Todo、FeedMessage 可访问但未提取 |
| 通过 `**kwargs` 但被 `extra='ignore'` 丢弃 | 2 | Memory/Recall、ToolDiscovery |
| 通过显式命名参数接收 | 1 | McpToolWrapper 签名中直接声明 cancel_event |
| 通过 `kwargs.get("cancel_event")` 直接提取 | 1 | SubAgent constructor 绕过 Pydantic 提取 |

---

## 三、逐工具详细分析

### 3.1 Bash — `/api/agent/tools/bash/` ✅ 已修复 (2025-06-25)

| 维度 | 详情 |
|------|------|
| **cancel_event 可访问** | 是，通过 `cast(asyncio.Event \| None, kwargs.get("cancel_event"))` 显式提取 |
| **实际检查** | ✅ **检查**。两处：入口 fast-return（`cancel_event.is_set()` → 立即返回）、`execute_command` 轮询循环（`asyncio.wait` 并发等待 cancel_event） |
| **长时间操作** | `execute_command()` → K8s Pod exec WebSocket → 可能运行数十分钟 |
| **替代中断机制** | `PodCommandSession.interrupt_event`（`threading.Event`），由 Pod 状态异常或超时触发 |
| **cancel_event ↔ interrupt_event 桥接** | ✅ **已桥接**。`execute_command` 检测到 cancel_event → 设置 interrupt_event → 发送 SIGINT |

**执行链路**：
```
BashTool.__call__(**kwargs)
  ├─ cancel_event.is_set()? → 立即返回 "Bash 命令已被用户取消"   # fast-return
  └─ pod_command_session(...) / execute_command(cancel_event=...)
       ├─ cancel_event=None? → 原有阻塞轮询
       └─ cancel_event 有值? → asyncio.wait(ws_update, cancel_event.wait())
            ├─ ws_update 完成 → 读取输出，继续循环
            └─ cancel_event.is_set() → interrupt_event.set() → break → SIGINT → interrupted=True
```

**取消延迟**：亚秒级（`asyncio.wait` 并发，不再受 5s 轮询间隔限制）。

**可取消性评级**：🟢 **可取消**（零延迟，SIGINT 直达容器）

---

### 3.2 SubAgent — `/api/agent/tools/sub_agent/`

| 维度 | 详情 |
|------|------|
| **cancel_event 可访问** | 是，通过 `kwargs.get("cancel_event", None)` 直接提取（**未使用** `cast()`，与其他工具风格不一致）并传给 `SubAgentRunner` |
| **入口 fast-return** | ❌ **缺失**。`SubAgentTool.__call__` 未在入口检查 `cancel_event.is_set()`（Bash/FileOps/MCP 均有此检查） |
| **实际检查** | ❌ 不检查。`SubAgentRunner` 存储 `self.cancel_event` 但自身方法体中无任何 `is_set()` 调用 |
| **长时间操作** | 启动异步子代理任务（`asyncio.create_task`），子代理独立运行整个 LLM 对话循环 |
| **替代中断机制** | 子代理拥有自己独立的 `cancel_event`（通过 `chat_task.py` 订阅自己的 Redis channel） |

**父子联动分析**：
```
父代理 cancel_event 被 set
  → SubAgentRunner 不检查（继续等待子代理返回 ToolTaskResult）
  → 子代理独立运行，有自己独立的 session_task_canceling:{sub_task_id}
  → 父取消不传播到子代理
  → 子代理完成后 _completed_callback 仍会向父分支插入消息
```

**Fork 模式的 cancel_event 传递**：
- `_run_fork`（`agent_runner.py` 第 283 行）将 `self.cancel_event` 传递给 `schedule_pending_task(...)`，使 pending task 等待可被父取消中断
- 但 `schedule_pending_task_canceled` channel **仍无发布者**（全代码库搜索无结果）
- 实际只能靠父任务完成或 10 分钟超时退出等待

**Standalone 模式**：`_run_standalone` 方法中 `self.cancel_event` 完全不被引用，父取消对该模式无任何影响。

**可取消性评级**：🔴 **不可取消**（且父取消不传递给子代理，入口无 fast-return）

---

### 3.3 MCP — `/api/agent/tools/mcp/` ✅ 已修复 (2026-06-26)

| 维度 | 详情 |
|------|------|
| **cancel_event 可访问** | 是，作为 **显式命名参数** `cancel_event: asyncio.Event`（方法签名第 68 行） |
| **实际检查** | ✅ **检查**。两处：入口 fast-return（`cancel_event.is_set()` → 立即返回）、`call_tool` 竞态（`asyncio.wait` 并发等待 call_tool 与 cancel_event） |
| **长时间操作** | `connection.call_tool()` → JSON-RPC over HTTP → 可能阻塞数秒到数分钟 |
| **替代中断机制** | 取消时主动 cancel 待处理 task，使 MCP 调用立即返回 |

**执行链路**：
```
McpToolWrapper.__call__(exec_uuid, cancel_event, **kwargs)
  ├─ cancel_event.is_set()? → 立即返回 "MCP 工具调用已被用户取消"   # fast-return
  └─ call_tool_task = asyncio.create_task(self._raw_call(...))
       └─ asyncio.wait([call_tool_task, cancel_event.wait()], return_when=FIRST_COMPLETED)
            ├─ call_tool_task 完成 → 返回 MCP 响应
            └─ cancel_event.is_set() → call_tool_task.cancel() → 返回 "已被用户取消"
```

**取消延迟**：亚秒级（`asyncio.wait` 并发等待，无需等待 MCP 服务器响应）。

**可取消性评级**：🟢 **可取消**（入口 fast-return + asyncio.wait 竞态取消）

---

### 3.4 AskUser — `/api/agent/tools/ask_user/` ✅ 已修复 (2025-06-26)

| 维度 | 详情 |
|------|------|
| **cancel_event 可访问** | 是，通过 `cast(asyncio.Event \| None, kwargs.get("cancel_event"))` 显式提取 |
| **实际检查** | ✅ **检查**。`cancel_event` 传递给 `HIL_interrupt()`，`__interrupt` 内部三路 `asyncio.wait(recv, timeout, cancel)` |
| **长时间操作** | `HIL_interrupt()` — 等待用户在前端做出选择，可能阻塞数分钟 |
| **替代中断机制** | HIL 自身的 `HILInterruptCancelled` 异常，现已与 cancel_event 联动 |

**可取消性评级**：🟢 **可取消**（cancel_event 触发 → `HILInterruptCancelled` → 立即返回）

---

### 3.5 FileOperations — `/api/agent/tools/file_operations/`（7 个子工具）✅ 已修复 (2026-06-26)

| 子工具 | cancel_event 可访问 | 实际检查 | 长时间操作 |
|--------|-------------------|---------|-----------|
| read_file | 是（`cast()` 显式提取） | ✅ | JuiceFS SDK 读取 |
| write_file | 是（`cast()` 显式提取） | ✅ | JuiceFS SDK 写入 |
| edit_file | 是（`cast()` 显式提取） | ✅ | JuiceFS SDK 编辑 |
| list_directory | 是（`cast()` 显式提取） | ✅ | JuiceFS SDK 目录扫描 |
| move_file | 是（`cast()` 显式提取） | ✅ | JuiceFS SDK 移动 |
| copy_file | 是（`cast()` 显式提取） | ✅ | JuiceFS SDK 复制 |
| delete_file | 是（`cast()` 显式提取） | ✅ | JuiceFS SDK 删除 |

**修复方式**：
1. 工具层：`cast()` 提取 cancel_event + 入口 fast-return
2. 存储后端层：`JuiceFSSdkBackend` 所有 I/O 方法新增 `cancel_event` 参数，透传给 `pool.call()`
3. Worker 池层：`pool.call()` 新增 `cancel_event` 参数，通过 `asyncio.Event → threading.Event` 桥接使 `get_result()` 线程内检测取消，最大延迟 500ms。Worker 进程的同步 I/O 无法从外部中断，但等待线程会立即返回。

**可取消性评级**：🟢 **可取消**（入口 fast-return + 线程级取消等待，500ms 粒度）

---

### 3.6 Memory/Recall — `/api/agent/tools/memory/`

| 维度 | 详情 |
|------|------|
| **cancel_event 可访问** | ❌ **不可访问**。`ReturnMemoryRecallParamDefine` **无** `extra='allow'`，Pydantic 默认 `extra='ignore'` 静默丢弃 cancel_event |
| **实际检查** | ❌ 不检查（且无法检查） |
| **长时间操作** | 循环读取 memory 文件（JuiceFS I/O） |

**可取消性评级**：🔴 **不可取消**

---

### 3.7 SummarizationCompact — `/api/agent/tools/summarization_compact/` ✅ 已修复 (2026-06-26)

| 维度 | 详情 |
|------|------|
| **cancel_event 可访问** | ✅ **已修复**。在 Pydantic 验证前通过 `cast(asyncio.Event \| None, kwargs.get("cancel_event"))` 显式提取 |
| **实际检查** | ✅ **检查**。三处：入口 fast-return、B1（断点）后、状态收集后。取消时通过 `rollback_marker` 回滚所有已注入节点 |
| **长时间操作** | `collect_and_inject_post_compression_state()` — 文件读取（JuiceFS）、DB 查询、技能重载 |

**修复方式**：
1. 工具层：`cast()` 提取 cancel_event + 入口 fast-return（Bash/FileOps 模式）
2. 回滚机制：`MemoryTrails.rollback_marker()` — 取消时将 marker 回滚到压缩前的 savepoint，撤销已注入的 context_breakpoint 和状态消息
3. 统一清理：`try/finally` 保证所有退出路径都清理 `tool_choice_steering` 和 `_tool_steering_block_stop`
4. 状态收集透传：`_collect_key_files` → `storage_backend.read_file()` 传递 cancel_event（JuiceFS `pool.call()` 已支持，仅需透传）

**执行链路**：
```
closure(**kwargs)
  ├─ cancel_event.is_set()? → 立即返回                           # fast-return #1
  ├─ model_validate(kwargs)
  ├─ savepoint = marker leaf                                    # 记录回滚点
  ├─ append_to_marker(is_context_breakpoint=True)                # B1
  ├─ cancel_event.is_set()? → rollback_marker(savepoint) → 返回  # 回滚断点
  ├─ collect_and_inject_post_compression_state(cancel_event=...)
  │    ├─ _collect_tool_enable_status  [纯内存]
  │    ├─ cancel check → return
  │    ├─ _collect_todo_state          [DB 查询]
  │    ├─ cancel check → return
  │    ├─ _collect_skills_state        [文件扫描 + 逐技能读]
  │    ├─ cancel check → return
  │    └─ _collect_key_files          [逐文件 read_file(cancel_event=...)]
  ├─ cancel_event.is_set()? → rollback_marker(savepoint) → 返回  # 回滚全部
  └─ 成功
finally: tool_choice_steering.discard + _tool_steering_block_stop = False
```

**可取消性评级**：🟢 **可取消**（savepoint/rollback 保证取消后 marker 状态完全恢复，granularity 受限于状态收集步骤间检查点）

---

### 3.8 Todo — `/api/agent/tools/todo/`

| 维度 | 详情 |
|------|------|
| **cancel_event 可访问** | 是（通过 `**kwargs` + `extra='allow'`） |
| **实际检查** | ❌ 不检查 |
| **长时间操作** | 全量读取+写入模式（`get_all_todos()` → 修改 → `save_all_todos()`），两次 DB 调用 |

**可取消性评级**：🟡 **低风险**（操作通常很快，取消不敏感）

---

### 3.9 Skills — `/api/agent/tools/skills/`

| 子工具 | cancel_event 可访问 | 实际检查 | 长时间操作 |
|--------|-------------------|---------|-----------|
| load_skill | 是 (`extra='allow'`) | ❌ | 扫描技能文件 + DB 写入 |
| unload_skill | 是 (`extra='allow'`) | ❌ | DB 写入（快速） |

**可取消性评级**：🟡 **中低风险**（load 可能较慢但通常可接受）

---

### 3.10 DynamicTool — `/api/agent/tools/dynamic_tool_DI/`

| 维度 | 详情 |
|------|------|
| **cancel_event 可访问** | 取决于用户定义的 `tool_param_model` 是否设置 `extra='allow'` |
| **实际检查** | ❌ 不检查 |
| **长时间操作** | 委托给用户提供的 `call_back()`，时长完全不可控 |

**可取消性评级**：🔴 **不可取消**（且行为取决于用户实现）

---

### 3.11 FeedMessage — `/api/agent/tools/feed_message/`

| 维度 | 详情 |
|------|------|
| **cancel_event 可访问** | 是（通过 `**kwargs` + `extra='allow'`） |
| **实际检查** | ❌ 不检查 |
| **长时间操作** | DB 写入 + 可选的 `asyncio.create_task(schedule_pending_task(...))` |

**可取消性评级**：🟡 **低风险**（操作通常很快）

---

### 3.12 ToolDiscovery — `/api/agent/tools/tool_discovery/`

| 维度 | 详情 |
|------|------|
| **cancel_event 可访问** | ❌ **不可访问**。`ToolDiscoveryToolParamDefine` 无 `extra='allow'` |
| **实际检查** | ❌ 不检查（且无法检查） |
| **长时间操作** | 纯内存操作（正则/BM25 搜索），无 I/O |

**可取消性评级**：🟢 **不敏感**（纯内存操作，瞬时完成）

---

### 3.13 ToolFactory — `/api/agent/tools/tool_factory/`

工厂类，不直接执行工具。不涉及 cancel_event 处理。**不适用**。

---

## 四、汇总矩阵

| # | 工具 | cancel_event 可访问 | 检查 is_set() | 长时间操作 | 风险等级 |
|---|------|-------------------|--------------|-----------|---------|
| 1 | **Bash** | 是（显式提取） | ✅ 已修复 | K8s Pod exec | 🟢 已修复 |
| 2 | **SubAgent** | 是（显式提取，无 fast-return） | ❌ | 完整 LLM 对话 | 🔴 高 |
| 3 | **MCP** | 是（显式参数） | ✅ 已修复 | HTTP RPC 调用 | 🟢 已修复 |
| 4 | AskUser | 是 | ✅ 已修复 | HIL 等待 | 🟢 已修复 |
| 5 | FileOps (×7) | 是 | ✅ 已修复 | JuiceFS I/O | 🟢 已修复 |
| 6 | Memory/Recall | ❌ 被丢弃 | ❌ | JuiceFS 文件读取 | 🟡 中 |
| 7 | SummarizationCompact | 是（显式提取，savepoint/rollback） | ✅ 已修复 | 状态收集 I/O | 🟢 已修复 |
| 8 | Skills | 是 | ❌ | 文件扫描 + DB | 🟡 中低 |
| 9 | Todo | 是 | ❌ | 全量读写 DB | 🟡 低 |
| 10 | FeedMessage | 是 | ❌ | DB 写入 | 🟡 低 |
| 11 | DynamicTool | 取决于用户 | ❌ | 用户回调 | 🔴 不确定 |
| 12 | ToolDiscovery | ❌ 被丢弃 | ❌ | 无（内存操作） | 🟢 无 |
| 13 | ToolFactory | N/A | N/A | N/A | N/A |

---

## 五、问题分类与根因分析

### 5.1 Pydantic 参数过滤问题（可访问性缺陷）

3 个工具的 Pydantic 参数模型**未设置** `extra='allow'`，导致 `cancel_event` 被静默丢弃：

| 工具 | 参数模型文件 | 修复方式 |
|------|------------|---------|
| Memory/Recall | `config_data_model.py:ReturnMemoryRecallParamDefine` | 添加 `model_config = ConfigDict(extra='allow')` |
| SummarizationCompact | ~~`config_data_model.py:SummarizationCompactParamDefine`~~ | ✅ 已修复 — 在 Pydantic 验证前通过 `kwargs.get()` 提取，无需改模型 |
| ToolDiscovery | `config_data_model.py:ToolDiscoveryToolParamDefine` | 添加 `model_config = ConfigDict(extra='allow')` |

### 5.2 工具取消检查覆盖率不足（行为性缺陷）

已修复的工具（Bash、MCP、AskUser、FileOperations×7）均遵循相似模式：`cast()` 提取 → 入口 fast-return → 下游透传 / `asyncio.wait` 竞态。但仍有多数工具（SubAgent、Skills、Todo、FeedMessage、Memory/Recall、DynamicTool）不检查 cancel_event。根因：

1. **工具框架未强制要求**：`ToolClosure` 类型为 `Callable[..., Coroutine[Any, Any, ToolTaskResult]]`，无取消检查契约
2. **工具开发者无感知**：cancel_event 作为被注入的基础设施参数，但工具开发者可能不知道它的存在
3. **缺少通用模式**：没有提供 `check_cancel()` 辅助函数或装饰器来统一处理取消
4. **修复模式已形成但未推广**：Bash/MCP/FileOps 的修复模式（入口 fast-return + 下游透传/竞态）可作为模板，但尚未推广到剩余工具

### 5.3 Bash 的机制分裂问题 ✅ 已修复 (2025-06-25)

~~Bash 工具形成了一套**完全独立的中断体系**~~：

现在两条路径已统一：
- 用户取消 → Redis → asyncio.Event（`cancel_event`）→ `execute_command` 检测 → 设置 `interrupt_event` → SIGINT 到容器
- Pod 异常/超时 → threading.Event（`interrupt_event`）→ SIGINT 到容器

修复方式：`cancel_event` 下沉到 `execute_command` 轮询循环中，通过 `asyncio.wait` 并发等待 WebSocket update 和 cancel_event，实现亚秒级取消响应。

### 5.4 SubAgent 的父子隔离问题（架构性缺陷）

子代理拥有独立的 `session_chat_task` 和独立的 `session_task_canceling:{sub_task_id}` channel。父代理取消时：
- 子代理不在父代理的 cancel_event 检查范围内（子代理不在父代理的 LLM 循环中）
- 需要**显式调用** `/cancel_session_task` 并传入子代理的 `session_task_id` 才能取消子代理
- 系统中没有任何代码自动发布子代理的取消信号

---

## 六、改进建议

### 高优先级

1. **~~Bash 工具添加 cancel_event ↔ interrupt_event 桥接~~** ✅ 已完成  
   已通过将 `cancel_event` 下沉到 `execute_command` 轮询循环中解决。用户取消时，`asyncio.wait` 并发检测并在亚秒级内向 Pod 发送 SIGINT。

2. **SubAgent 取消传播**  
   当父代理的 `cancel_event` 被设置时，应发布 `session_task_canceling:{sub_task_id}` 到 Redis，以取消正在运行的子代理。

3. **~~McpToolWrapper 添加取消检查~~** ✅ 已完成  
   已实现入口 fast-return + `asyncio.wait([call_tool_task, cancel_event.wait()])` 竞态取消模式。

### 中优先级

4. **统一工具取消检查点**  
   在 `_execute_tool_calls` 中添加 `cancel_event` 的并发监听，取消时主动 cancel 运行中的工具 asyncio.Task。

5. **补全 `schedule_pending_task_canceled` 发布者**  
   在 `cancel_session_task.py` 或 `chat_task.py` 的取消处理中发布该事件。

6. **Pydantic 模型统一配置**  
   为 `memory/recall`、`tool_discovery` 的参数模型添加 `extra='allow'`（summarization_compact 已通过在 Pydantic 前提取解决）。

### 低优先级

7. **工具接口契约化**  
   在 `ToolClosure` 类型或工具基类中明确 cancel_event 的检查和响应要求。

8. **提供 `check_cancel` 辅助函数**  
   在工具基类或 util 中提供统一的异步取消检查函数。

---

## 七、涉及文件清单

| 文件 | 角色 |
|------|------|
| `api/agent/base_agent.py` | cancel_event 注入点 + LLM 流式循环中的检查点 |
| `api/agent/tools/bash/constructor.py` | Bash 工具：✅ 已修复 — 提取 cancel_event + fast-return + 传递给 execute_command |
| `api/user_pod_command/executor.py` | Pod 命令执行器：✅ 已修复 — 接收 cancel_event + asyncio.wait 并发检测 |
| `api/user_pod_command/context_manager.py` | Pod 会话管理：设置 interrupt_event |
| `api/user_pod_command/data_model.py` | PodCommandSession 定义 interrupt_event |
| `api/agent/tools/sub_agent/constructor.py` | SubAgent 工具：提取 cancel_event（kwargs.get，非 cast()）但无入口 fast-return，未检查 |
| `api/agent/tools/sub_agent/agent_runner.py` | SubAgentRunner：存储 cancel_event，standalone 模式完全不引用，fork 模式仅透传给 schedule_pending_task |
| `api/agent/tools/mcp/tool_mapper.py` | MCP 工具包装器：✅ 已修复 — 显式命名参数接收 cancel_event + 入口 fast-return + asyncio.wait 竞态取消 |
| `api/agent/tools/ask_user/constructor.py` | AskUser 工具：✅ 已修复 — cast() 提取 cancel_event + 传递给 HIL_interrupt |
| `api/agent/tools/file_operations/*/constructor.py` (×7) | FileOps 工具：✅ 已修复 — cast() 提取 cancel_event + fast-return + 传递给后端 |
| `api/agent/tools/file_operations/storage_backend/base.py` | 存储后端基类：✅ 已修复 — 所有抽象方法新增 cancel_event 参数 |
| `api/agent/tools/file_operations/storage_backend/juicefs_sdk.py` | JuiceFS SDK 后端：✅ 已修复 — 所有 I/O 方法透传 cancel_event |
| `api/juiceFS/client_worker/pool.py` | Worker 池：✅ 已修复 — call() 新增 cancel_event + asyncio→threading 桥接；get_result() 500ms 短轮询 |
| `api/juiceFS/client_worker/exceptions.py` | 异常定义：✅ 已修复 — 新增 TaskCancelledError |
| `api/agent/tools/feed_message/constructor.py` | FeedMessage 工具：cancel_event 进入 model_extra，未提取 |
| `api/agent/tools/todo/constructor.py` | Todo 工具：cancel_event 进入 model_extra，未提取 |
| `api/agent/tools/skills/load_skill/constructor.py` | LoadSkill 工具：cancel_event 进入 model_extra，未提取 |
| `api/agent/tools/skills/unload_skill/constructor.py` | UnloadSkill 工具：cancel_event 进入 model_extra，未提取 |
| `api/agent/tools/dynamic_tool_DI/constructor.py` | DynamicTool：cancel_event 传递取决于用户 |
| `api/agent/tools/memory/recall/config_data_model.py` | 缺少 `extra='allow'` |
| `api/agent/tools/summarization_compact/tool_closure.py` | SummarizationCompact 工具：✅ 已修复 — cast() 提取 cancel_event + savepoint/rollback + try/finally 统一清理 |
| `api/agent/tools/summarization_compact/state_collector.py` | 状态收集器：✅ 已修复 — 步骤间 cancel 检查点 + _collect_key_files 透传 cancel_event 给 read_file() |
| `api/agent/memory_trails/trails.py` | MemoryTrails：✅ 已修复 — 新增 rollback_marker() 方法支持回滚到指定节点 |
| `api/agent/tools/tool_discovery/config_data_model.py` | 缺少 `extra='allow'` |
| `api/chat/exception.py` | SessionChatTaskCancelled 异常定义 |
| `api/redis/pub_channel_name.py` | Channel 名称定义（含未使用的 schedule_pending_task_canceled） |
