# 候选：SubAgentRunner 多步初始化合并为原子事务

**状态**: 待审查（代码修改完成，等待用户审查）
**发现日期**: 2026-07-12
**优先级建议**: P1

## 涉及文件

- `api/agent/tools/sub_agent/agent_runner.py` — 改造主战场
- `api/chat/sql_stat/u2a_session_branch_task/operations.py` — 所有 operation 函数已 ctx 改造（无需修改）
- `api/chat/sql_stat/u2a_session_branch_task/storage_snapshot_op.py` — `update_branch_storage_snapshot` 已 ctx 改造（无需修改）
- `api/chat/sql_stat/u2a_session_task/utils.py` — `get_task`, `update_task_storage_snapshot`, `merge_task_logic_mark` 已 ctx 改造（无需修改）
- `api/chat/sql_stat/u2a_user_msg/utils.py` — `insert_user_messages_from_list` 已 ctx 改造（无需修改）
- `api/agent/session_agent_config/crud.py` — `update_config_overlay` 内部调用 `update_task_storage_snapshot`，透传 ctx 即可

## 当前调用链

两个方法 `_run_standalone` 和 `_run_fork` 结构几乎一致，以 `_run_standalone` 为例：

```
_run_standalone(task, should_feedback)
  │
  ├─ (1) create_root_task_with_branch(...)             [独立 commit ← SQL_OP_ContextData 内部]
  │      └─ 返回 (branch_id, root_task_id)
  │
  ├─ (2) update_branch_storage_snapshot(...)            [独立 commit ← 内部 get_or_create + get_task + update_task_storage_snapshot]
  │      └─ 写入 SUB_AGENT_ALIASES 到调用方分支的 storage_snapshot
  │
  ├─ (3) get_task(root_task_id)                         [纯读]
  │
  ├─ (4) update_config_overlay(root_task_id, ...)       [独立 commit ← 内部 update_task_storage_snapshot]
  │      └─ 写入 SESSION_CONFIG_OVERLAY 到 root task 的 storage_snapshot
  │
  ├─ (5) merge_task_logic_mark(task_id, {...})           [独立 commit]
  │      └─ 设置 tool_enable_status / mcp_config / branch_changed 标记
  │
  └─ (6) insert_user_messages_from_list(messages)       [独立 commit]
         └─ 批量插入 4 条用户消息
```

`_run_fork` 同理，仅步骤 1 换为 `fork_branch(...)`。

## 当前风险

### 方法返回后调用方失败

`_run_standalone` 方法 return 后，调用方 `__call__` 会构造 `ToolTaskResult` 返回。如果调用方后续在返回 ToolTaskResult 前异常，已 commit 的 branch/task/messages 成为孤儿。

### 中间步骤异常：最严重的场景

| 步骤 1 | 步骤 2 | 步骤 3 | 步骤 4 | 步骤 5 | 步骤 6 | 结果 |
|--------|--------|--------|--------|--------|--------|------|
| OK     | OK     | OK     | FAIL   | -      | -      | **孤儿 branch + task**：已创建但无 config overlay、无 logic mark、无消息，后续 process_pending_messages 会在缺省配置下执行，行为不可预测 |
| OK     | OK     | OK     | OK     | FAIL   | -      | **半初始化 task**：有 config overlay 但缺 logic marks（工具启用状态、MCP 配置、分支变更标记未设），process_pending_messages 可能跳过必要的系统提醒 |
| OK     | OK     | FAIL   | -      | -      | -      | **孤儿 branch + task**：调用方分支无 SUB_AGENT_ALIASES 映射，后续 feed_message 无法通过别名投递消息到子代理分支 |
| OK     | FAIL   | -      | -      | -      | -      | 最干净：root task + branch 已创建，但异常可能来自 `update_branch_storage_snapshot` 内部的分布式锁超时，此时调用方方法 catch 不到，branch 成为永久的孤儿 |

### 其他风险

- `asyncio.create_task` 启动的 `_process_pending_messages` 与 `_completed_callback` 依赖步骤 1-6 全部成功，但这两行在 commit 边界之外，如果主协程在 `create_task` 后异常退出，子协程可能从半初始化状态开始处理
- 当前设计无法回滚——任何步骤失败，已提交的写入永久残留

## 改造方案

### ctx 创建位置

在 `SubAgentRunner.run()` 方法中创建 `SQL_OP_ContextData`，通过函数参数透传给 `_run_standalone` / `_run_fork`，最终在 `run()` 返回时统一 commit。异常时依赖 `SQL_OP_ContextData` 的 `async with` 上下文管理器自动 rollback。

### ctx 作用域

从 `run()` 入口开始，覆盖 `_run_standalone` / `_run_fork` 全部的 DB 写操作。由于两个方法内部的 `asyncio.create_task(...)` 是 fire-and-forget 的异步调度（非 DB 操作），不需要在 ctx 作用域内。

**注意**：`_process_pending_messages` 的 `create_task` 本身不是 DB 操作，但被调度协程内部会执行 DB 写入。这些写入应该由被调度协程自己管理 ctx（保持现状），不纳入当前 ctx。

### 跨模块透传

所有被调用的底层函数（operations.py, storage_snapshot_op.py, utils.py 等）**已经支持 `ctx` 参数**，无需修改。只需在 `agent_runner.py` 中：

1. 创建 `SQL_OP_ContextData` 实例
2. 向每个 DB 调用传入 `ctx=ctx`
3. `session_agent_config/crud.py` 中的 `update_config_overlay` 目前内部调用 `update_task_storage_snapshot(task_id, storage_snapshot)` **不传 ctx**，需要增加 ctx 透传

### 异常处理调整

当前两个方法在异常发生时没有 try/except，异常直接向上抛给 `run()` → `__call__`。改造后用 `async with ctx:` 包裹 DB 写入段，异常自动 rollback。方法结构变为：

```python
async def run(self, task, context_mode, should_feedback):
    ctx = SQL_OP_ContextData()
    async with ctx:
        if context_mode == "fork":
            return await self._run_fork(task, should_feedback, ctx=ctx)
        return await self._run_standalone(task, should_feedback, ctx=ctx)
```

### 需要额外改造的模块

`session_agent_config/crud.py` 中的 `update_config_overlay` 需要增加 `ctx` 参数并透传给 `update_task_storage_snapshot`：

```python
async def update_config_overlay(
    task_id: UUID,
    storage_snapshot: dict,
    overlay_updates: dict,
    ctx: SQL_OP_ContextData | None = None,  # 新增
) -> dict:
    merge_config_overlay(storage_snapshot, overlay_updates)
    await update_task_storage_snapshot(task_id, storage_snapshot, ctx=ctx)  # 透传 ctx
    return storage_snapshot
```

## 伪代码

### 改造前（_run_standalone 当前代码）

```python
async def _run_standalone(self, task, should_feedback):
    sub_branch_name = construct_branch_name(f"__sub_agent_{self.agent_def.name}")

    # 步骤 1-6 各自独立 commit，中间失败无法回滚
    _branch_id, root_task_id = await create_root_task_with_branch(
        session_id=self.session_id, user_id=self.user_id,
        name=sub_branch_name, created_by="agent",
    )

    await update_branch_storage_snapshot(
        session_id=self.session_id, user_id=self.user_id,
        branch_name=self.branch_name,
        update_fn=lambda snap: _register_sub_agent_session(snap, sub_branch_name),
    )

    overlay = await self._build_config_overlay(should_feedback)
    root_task = await get_task(root_task_id)
    await update_config_overlay(
        root_task_id,
        dict(root_task.storage_snapshot) if root_task and root_task.storage_snapshot else {},
        overlay,
    )

    await self._set_logic_marks(root_task_id)

    contents = await self._build_messages(task, should_feedback)
    messages = [_U2AUserMessageCreate(...) for msg_content in contents]
    await insert_user_messages_from_list(messages)

    # fire-and-forget 调度（非 DB，不纳入事务）
    asyncio.create_task(_process_pending_messages(...))
    ...
```

### 改造后

```python
async def _run_standalone(self, task, should_feedback,
                          ctx: SQL_OP_ContextData) -> ToolTaskResult:
    sub_branch_name = construct_branch_name(f"__sub_agent_{self.agent_def.name}")

    # 步骤 1-6 共享同一个 ctx，commit 由最外层统一执行
    _branch_id, root_task_id = await create_root_task_with_branch(
        session_id=self.session_id, user_id=self.user_id,
        name=sub_branch_name, created_by="agent",
        ctx=ctx,
    )

    await update_branch_storage_snapshot(
        session_id=self.session_id, user_id=self.user_id,
        branch_name=self.branch_name,
        update_fn=lambda snap: _register_sub_agent_session(snap, sub_branch_name),
        ctx=ctx,
    )

    overlay = await self._build_config_overlay(should_feedback)
    root_task = await get_task(root_task_id, ctx=ctx)
    await update_config_overlay(
        root_task_id,
        dict(root_task.storage_snapshot) if root_task and root_task.storage_snapshot else {},
        overlay,
        ctx=ctx,
    )

    await self._set_logic_marks(root_task_id, ctx=ctx)  # 签名加 ctx，透传给 merge_task_logic_mark

    contents = await self._build_messages(task, should_feedback)
    messages = [_U2AUserMessageCreate(...) for msg_content in contents]
    await insert_user_messages_from_list(messages, ctx=ctx)

    # fire-and-forget 调度仍在 ctx 外部，保持独立事务
    # （这些 asyncio.create_task 不是 DB 操作，不受 ctx 影响）

    return ToolTaskResult(...)
```

`run()` 方法变为：

```python
async def run(self, task, context_mode, should_feedback):
    ctx = SQL_OP_ContextData()
    async with ctx:
        if context_mode == "fork":
            return await self._run_fork(task, should_feedback, ctx=ctx)
        return await self._run_standalone(task, should_feedback, ctx=ctx)
```

`_run_fork` 同理，签名增加 `ctx: SQL_OP_ContextData`，所有 DB 调用透传 `ctx=ctx`。

## 注意事项

1. **`_completed_callback` 不纳入事务**：该方法是 `asyncio.create_task` 调度的异步回调，运行在独立协程中，不应共享 `run()` 的 ctx。它内部的 `get_or_create_pending_task` + `insert_user_message` 是一次性的独立通知写入，保持现有独立 commit 行为即可。

2. **`asyncio.create_task(_process_pending_messages(...))` 不纳入事务**：`_process_pending_messages` 内部有大量 DB 读写（消息处理、agent 循环、工具执行），是长时间运行的后台协程。它在 ctx commit 前被 `create_task` 调度，但实际执行在 ctx commit 后的某个时刻，无需也无法纳入当前 ctx。

3. **`schedule_pending_task` 在 `_run_fork` 中的位置**：`_run_fork` 用 `schedule_pending_task`（非 `_process_pending_messages`）来调度处理，这一样是 `asyncio.create_task` 调度的，不纳入 ctx。但需要注意 `schedule_pending_task` 内部会写 `status="processing"` 到 task——这是独立事务，如果 ctx 最终 rollback，task 的 status 已是 processing，会形成不一致状态。但由于 `ctx.rollback()` 后 task 本身被回滚（不存在），processing 状态的写入是针对不存在的 task 行（由 `create_root_task_with_branch` 插入），rollback 后该行不存在，所以 schedule_pending_task 内部的 `UPDATE ... SET status='processing'` 将匹配不到行。**但仍需验证**：schedule_pending_task 在 `create_task` 中调度，可能在 ctx commit 之前或之后执行。如果它先执行（ctx 尚未 commit/rollback），它会读取到未提交的 task 行并写入 processing；如果 ctx 随后 rollback，task 行消失但 processing 写入已提交到独立的 schedule_pending_task 事务中——这不会产生孤儿数据（因为 task 行已 rollback），但会留下一条无意义的 status 变更日志。建议在 ctx commit 之后再 `create_task(schedule_pending_task(...))`，即将调度移至 `async with ctx:` 块之外。

4. **`session_agent_config/crud.py` 的 ctx 透传**：`update_config_overlay` 当前内部调用 `update_task_storage_snapshot(task_id, storage_snapshot)` 不传 ctx。需要增加 `ctx` 参数并透传。该模块还有 `get_base_session_config` 和 `get_effective_session_config`（纯读/纯内存，不需要改）。

5. **`_set_logic_marks` 辅助方法**：当前签名 `(self, task_id: UUID)`，内部调用 `merge_task_logic_mark(task_id, ...)` 不传 ctx。需要增加 ctx 参数并透传。

6. **改造影响范围**：仅 `agent_runner.py` 和 `session_agent_config/crud.py` 两个文件需要修改，所有底层 sql_stat utils 已支持 ctx 参数，无需改动。

7. **与非 ctx 路径的兼容性**：ctx 参数的默认值 `None` 保证现有调用方（如直接调用 `_run_standalone` 的其他代码路径）不受影响。
