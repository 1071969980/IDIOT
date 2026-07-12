# 候选：UpdateToolsStatus 存储快照与逻辑标记原子化

**状态**: 已完成
**发现日期**: 2026-07-12
**优先级建议**: P1

## 涉及文件

| 文件 | 角色 |
|---|---|
| `api/app/chat/session_agent_config/command/update_tools_status/command.py` | 业务层 — 两处独立 DB 写 |
| `api/app/chat/sql_stat/u2a_session_branch_task/storage_snapshot_op.py` | 中间层 — `update_branch_storage_snapshot` 缺少 ctx 透传 |
| `api/app/chat/sql_stat/u2a_session_task/utils.py` | 底层 — `update_task_storage_snapshot` / `update_task_logic_mark_field` 均已支持 ctx |

## 当前调用链

```
UpdateToolsStatusCommand.execute()
  │
  ├─[1] await update_branch_storage_snapshot(session_id, user_id, branch_name, update_fn)
  │     内部:
  │       ├─ get_or_create_pending_task(...)       → 独立 conn/commit（ctx=None）
  │       ├─ RedisDistributedLock(...)              → 进程间互斥锁
  │       └─ update_task_storage_snapshot(task_id, snapshot)  → 独立 conn/commit（ctx=None）
  │
  └─[2] await update_task_logic_mark_field(task_id, TO_REMINDER_TOOL_ENABLE_STATUS_MARK_NAME, True)
        内部:
           └─ _resolve_conn(ctx=None) → 独立 conn/commit
```

**关键事实**：步骤 [1] 和步骤 [2] 各自独立提交，中间无事务包裹。

## 当前风险

**半写入状态** — 如果步骤 [1] 成功（storage_snapshot 已更新为新的工具启用状态）但步骤 [2] 失败（logic_mark `TO_REMINDER_TOOL_ENABLE_STATUS_MARK_NAME` 未设置为 `True`），则：

- 下游任何依赖 `TO_REMINDER_TOOL_ENABLE_STATUS_MARK_NAME` 标记来判断"工具状态是否已变更"的逻辑会得到错误结论（认为未变更）
- storage_snapshot 状态与 logic_mark 产生永久性不一致
- 无回滚机制（分布式锁保护的是 task 级别并发写入，不覆盖跨操作的原子性）

场景可能触发：
- 步骤 [2] 执行时 DB 连接断开
- 步骤 [2] 执行时 PG 抛出异常（如 deadlock detected）
- 进程在步骤 [1] 和 [2] 之间被 SIGKILL

## 改造方案

**核心思路**：在 `execute()` 方法中创建一个 `SQL_OP_ContextData`，透传给 `update_branch_storage_snapshot` 和 `update_task_logic_mark_field`，使两个写入在同一事务中原子提交。

**改造步骤**：

### 1. `storage_snapshot_op.py` — 新增 ctx 透传

为 `get_branch_storage_snapshot` 和 `update_branch_storage_snapshot` 添加 `ctx` 参数，并透传给底层调用：

- `get_or_create_pending_task(..., ctx=ctx)`
- `get_task(..., ctx=ctx)`
- `update_task_storage_snapshot(..., ctx=ctx)`

### 2. `update_tools_status/command.py` — 创建 ctx 包裹两处写入

在 `execute()` 中：
1. 创建 `ctx = SQL_OP_ContextData()`
2. `try` 块中调用 `update_branch_storage_snapshot(..., ctx=ctx)` 和 `update_task_logic_mark_field(..., ctx=ctx)`
3. 成功后 `await ctx.commit()`
4. `except` 中 `await ctx.rollback()` 后重新抛出

### 3. 其他调用方 — 无需修改

由于 `ctx` 参数默认值为 `None`，`get_branch_storage_snapshot` 和 `update_branch_storage_snapshot` 的所有现存调用方（共约 15+ 处，分布在 `api/agent/tools/` 下多个文件）无需任何修改即可正常工作。

## 伪代码

```python
# === storage_snapshot_op.py ===

async def get_branch_storage_snapshot(
    session_id: UUID,
    user_id: UUID,
    branch_name: str,
    ctx: SQL_OP_ContextData | None = None,           # 新增
) -> tuple[UUID, dict[str, Any]]:
    task_id, _ = await get_or_create_pending_task(
        session_id=session_id,
        user_id=user_id,
        branch_name=branch_name,
        ctx=ctx,                                      # 透传
    )
    task = await get_task(task_id, ctx=ctx)            # 透传
    if task is None or task.storage_snapshot is None:
        raise ValueError(f"Task {task_id} or its storage_snapshot not found")
    return task_id, dict(task.storage_snapshot)


async def update_branch_storage_snapshot(
    session_id: UUID,
    user_id: UUID,
    branch_name: str,
    update_fn: Callable[[dict[str, Any]], bool],
    ctx: SQL_OP_ContextData | None = None,           # 新增
) -> tuple[UUID, dict[str, Any]]:
    task_id, _ = await get_or_create_pending_task(
        session_id=session_id,
        user_id=user_id,
        branch_name=branch_name,
        ctx=ctx,                                      # 透传
    )
    lock_key = LockNames.task_storage_snapshot(task_id)
    async with RedisDistributedLock(lock_key, allow_multi_lock=True):
        task = await get_task(task_id, ctx=ctx)        # 透传
        if task is None or task.storage_snapshot is None:
            raise ValueError(...)
        snapshot = dict(task.storage_snapshot)
        should_save = update_fn(snapshot)
        if should_save:
            await update_task_storage_snapshot(task_id, snapshot, ctx=ctx)  # 透传
    return task_id, snapshot


# === update_tools_status/command.py ===

from api.sql_utils.utils import SQL_OP_ContextData    # 新增 import

async def execute(self) -> UpdateToolsStatusOutput:
    session_uuid = UUID(self.session_id)
    base_config = await get_base_session_config(session_uuid)

    # ... 验证工具名称（纯读，无需 ctx）...

    overlay_updates = {"tools_config": tools_overlay}

    ctx = SQL_OP_ContextData()                         # 新增
    try:
        task_id, storage_snapshot = await update_branch_storage_snapshot(
            session_id=session_uuid,
            user_id=UUID(self.user_id),
            branch_name=self.input_model.branch_name,
            update_fn=lambda s: merge_config_overlay(s, overlay_updates),
            ctx=ctx,                                    # 传入 ctx
        )

        await update_task_logic_mark_field(
            task_id, TO_REMINDER_TOOL_ENABLE_STATUS_MARK_NAME, True,
            ctx=ctx,                                    # 传入 ctx
        )

        await ctx.commit()                              # 新增：原子提交
    except Exception:
        await ctx.rollback()                            # 新增：异常回滚
        raise

    # ... 构建响应（纯读，无需 ctx）...
```

## 注意事项

1. **分布式锁与 SQL 事务的关系**：`update_branch_storage_snapshot` 内部使用 `RedisDistributedLock` 保护同一 task 的并发写入。ctx 事务跨越此锁不会导致死锁——Redis 锁和 PG 事务是正交的。
2. **`get_branch_storage_snapshot` 读函数无需 ctx**：虽然也加了 ctx 参数，但读操作本身不需要事务。加 ctx 仅为接口一致性，调用方可选择不传。
3. **现有 15+ 调用方零影响**：ctx 默认值为 `None`，所有现存调用保持原有行为（独立连接 + 自动提交）。
4. **事务范围仅覆盖 DB 操作**：`get_base_session_config`（读基础配置）、Redis 锁获取、响应构建均在事务外，事务仅包裹两步 DB 写入。
5. **禁止的做法**：不要在 `update_branch_storage_snapshot` 内部绕过 ctx 创建独立连接——所有底层函数都已支持 ctx，只需透传。
