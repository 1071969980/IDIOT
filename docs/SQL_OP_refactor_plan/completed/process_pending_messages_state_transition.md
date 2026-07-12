# 候选：process_pending_messages 任务/消息状态联动原子化

**状态**: 已完成
**发现日期**: 2026-07-12
**优先级建议**: P0

## 涉及文件

- `api/app/chat/process_pending_messages.py` — 业务入口 `_process_pending_messages`
- `api/chat/sql_stat/u2a_session_task/utils.py` — `update_task_status`（已 ctx 改造）
- `api/chat/sql_stat/u2a_user_msg/utils.py` — `update_user_message_status_by_ids`（已 ctx 改造）

## 当前调用链

在 `_process_pending_messages` 中（distributed lock 内部，process_pending_messages.py 第 103-184 行）：

```
async with RedisDistributedLock(...):                    # 分布式锁开始

  # … 多个读操作（无 commit）…

  await update_task_status(task_uuid, "processing")       # ① WRITE: task status → "processing"
                                                          #    独立获取连接，独立 commit

  await update_user_message_status_by_ids(                # ② WRITE: 多条 message status →
      [msg.id for ...], "agent_working_for_user"          #    "agent_working_for_user"
  )                                                       #    独立获取连接，独立 commit

# 分布式锁释放 ← 锁在此处退出

try:
    # init_tools, session_chat_task 创建
except Exception:
    # 回滚（两个独立 write，各自独立 commit）:
    await update_task_status(task_uuid, "pending")        # ③ ROLLBACK WRITE
    await update_user_message_status_by_ids(              # ④ ROLLBACK WRITE
        [msg.id for ...], "waiting_agent_ack_user"
    )
```

## 当前风险

**风险 1（WRITE ① 成功，WRITE ② 失败）**：
- task 已标记为 `processing`，但消息仍为 `waiting_agent_ack_user`
- 分布式锁释放后，另一个 `process_pending_messages` 调用可获取锁
- 该调用读到 task 状态为 `processing`（不是 pending），在步骤 3 处跳过
- 但如果还有并发情况或重试，状态不一致会导致逻辑混乱

**风险 2（WRITE ①、② 成功，但 init_tools / session_chat_task 创建失败，回滚写 ③ 成功而 ④ 失败）**：
- task 已回滚为 `pending`，但消息状态仍为 `agent_working_for_user`
- 下次调用会找到 pending task，但消息不满足 `waiting_agent_ack_user` 过滤条件
- 导致消息永远无法被处理

**风险 3（回滚写 ④ 成功而 ③ 失败）**：
- task 状态仍为 `processing`，但消息已回滚为 `waiting_agent_ack_user`
- task 被卡在 processing 状态，无法被再次处理

## 改造方案

- **ctx 创建位置**：`_process_pending_messages` 中，两个写操作之前
- **ctx 作用域**：覆盖 `update_task_status` 和 `update_user_message_status_by_ids` 两次写（同一事务）
- **是否需要跨模块透传**：是 — ctx 需要同时透传给 `update_task_status`（task utils）和 `update_user_message_status_by_ids`（user_msg utils）
- **异常处理调整**：正常路径的两个写改为事务包裹，一起 commit 或一起 rollback；回滚路径保持现有独立写入（已在 except 块中，且正常路径失败时事务已回滚，回滚路径重新执行独立写即可）

## 伪代码

### 改造前（当前代码，简化）

```python
async with RedisDistributedLock(...):
    # ... 读操作 ...

    # 两个独立写
    await update_task_status(task_uuid, "processing")
    await update_user_message_status_by_ids(
        [msg.id for msg in pending_messages], "agent_working_for_user"
    )

# 锁释放

try:
    # init_tools, create_task ...
except Exception:
    # 回滚：两次独立写
    await update_task_status(task_uuid, "pending")
    await update_user_message_status_by_ids(
        [msg.id for msg in pending_messages], "waiting_agent_ack_user"
    )
    raise
```

### 改造后（伪代码）

```python
async with RedisDistributedLock(...):
    # ... 读操作（不变）...

    # 创建共享 ctx 包裹两次写为原子事务
    ctx = SQL_OP_ContextData()
    try:
        await update_task_status(task_uuid, "processing", ctx=ctx)
        await update_user_message_status_by_ids(
            [msg.id for msg in pending_messages], "agent_working_for_user", ctx=ctx
        )
        await ctx.commit()
    except Exception:
        await ctx.rollback()
        raise

# 锁释放

try:
    # init_tools, create_task ...（不变）
except Exception:
    # 回滚：两次独立写（保持原有逐条执行方式，因为正常路径的事务已回滚）
    try:
        await update_task_status(task_uuid, "pending")
        await update_user_message_status_by_ids(
            [msg.id for msg in pending_messages], "waiting_agent_ack_user"
        )
    except Exception:
        pass
    raise
```

## 注意事项

- **分布式锁不变**：ctx 事务在锁内部创建和提交，锁的释放时机不受影响（在 try/commit 或 except/rollback 之后，锁正常退出）
- **跨模块 ctx 透传**：`update_task_status` 在 `api/chat/sql_stat/u2a_session_task/utils.py`，`update_user_message_status_by_ids` 在 `api/chat/sql_stat/u2a_user_msg/utils.py`，两者均已完成 ctx 改造，ctx 参数透传无阻
- **回滚路径不合并**：异常回滚路径的两次写保持原样（各自独立），因为正常路径的事务已经在 except 时 rollback，回滚路径的写是新操作，单独执行即可
- **无并发考虑**：分布式锁已保证单分支单次进入，ctx 事务不引入额外并发问题
- **_resolve_conn 的 auto_commit 行为**：ctx.auto_commit 默认为 True。传入 ctx 后，`_resolve_conn` 返回 ctx.conn 并跳过内部 commit（因为 `ctx.auto_commit` 为 True 时会自动 commit，但手动 commit 模式下应该设为 False）。根据 SPEC 要求，创建 ctx 时需设置 `auto_commit=False` 以实现手动控制提交时机
