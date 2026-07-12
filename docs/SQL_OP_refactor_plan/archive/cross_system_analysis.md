# 跨系统穿插文件分析报告

**分析日期**: 2026-07-12
**分析范围**: 7 个涉及"DB 写入与其他系统操作（K8s、Redis、bash 命令）穿插"的业务文件

## 总览

| 文件 | 穿插类型 | 有多步 DB 写 | 可改造性 | 建议 |
|------|---------|------------|---------|------|
| `api/user_pod_scheduler/scheduler.py` | DB + K8s | 是 | 部分可行 | 仅 `update_status`+`update_heartbeat` 对可 ctx 包裹，其余不可 |
| `api/user_pod_scheduler/heartbeat_checker.py` | 纯编排（调用 scheduler） | 否（无直接 DB 写） | N/A | 无需改造 |
| `api/chat/schedule_pending_task.py` | DB 读 + Redis Lock/Event | 否（纯读） | N/A | 无需改造 |
| `api/agent/tools/file_operations/file_hash_tracker.py` | DB + Redis | 否（单次 DB 写） | N/A | 每次 DB 写已是原子操作，无需 ctx |
| `api/system_notification/notification_service.py` | DB + Redis 双写 | 否（每函数最多 1 次 DB 写） | N/A | 无需改造（已在上一次评估中确认） |
| `api/system_notification_task/task_app.py` | DB + Redis | 否（单次 DB 写） | N/A | 无需改造 |
| `api/human_in_loop/http_worker/router.py` | DB 读 + Redis Stream | 否（无 DB 写） | N/A | 无需改造 |

**结论汇总**：7 个文件中，仅 1 个有部分可改造点（scheduler.py 中的一个两行代码块），其余 6 个均无可改造的多步 DB 写场景。

---

## 逐文件分析

### 1. `api/user_pod_scheduler/scheduler.py`

**当前调用链**：

函数 `create_or_start_user_pod`（第 90-219 行）：

```
1. query_record_by_user_id_and_image(...)         [DB 读]
2. if existing and status==RUNNING: return        [提前返回]
3. if existing and status==CREATING:
     _wait_and_handle_ready → update_status(RUNNING) [DB 写，单步]
4. check_juicefs_formatted(...)                   [K8s API]
5. create_juicefs_for_user(...)                   [K8s API / JuiceFS]
6. if not existing:
     insert_record(...)                            [DB 写，单步]
   else:
     update_status(CREATING)                       [DB 写 #1]
     update_heartbeat(...)                         [DB 写 #2 — 两写之间无外部操作]
7. create_juicefs_secret(...)                      [K8s API]
   ├─ 失败 → update_status(ERROR)                 [DB 写，单步]
8. create_storage_class(...)                       [K8s API]
   ├─ 失败 → update_status(ERROR)                 [DB 写，单步]
9. create_pvc(...)                                 [K8s API]
   ├─ 失败 → update_status(ERROR)                 [DB 写，单步]
10. create_user_pod(...)                           [K8s API，在内层锁内]
    ├─ 失败 → update_status(ERROR)                [DB 写，单步]
11. _wait_and_handle_ready → update_status(RUNNING/ERROR) [DB 写，单步]
```

函数 `unload_user_pod`（第 263-303 行）：

```
1. update_status(STOPPING)                        [DB 写 #1]
2. delete_user_pod_only(...)                      [K8s API]
3. if success:
     update_status_and_unload(STOPPED)             [DB 写 #2]
   else:
     update_status(ERROR)                          [DB 写 #2]
4. query_records_by_user_id(...)                   [DB 读]
5. if no_active: delete_user_k8s_resources(...)    [K8s API]
```

函数 `unload_all_user_pods`（第 310-337 行）：

```
for each record:
    1. update_status(STOPPING)                    [DB 写 #1]
    2. delete_user_pod_only(...)                   [K8s API]
    3. update_status_and_unload(STOPPED) 或 update_status(ERROR) [DB 写 #2]
4. delete_user_k8s_resources(...)                  [K8s API]
```

**现有补偿机制**：

- 每个 K8s 操作失败后，立即通过 `update_status(ERROR, message)` 将 DB 状态标记为 ERROR，携带失败原因。
- 外层 `try/except`（第 208 行）统一捕获异常，同样写入 ERROR 状态。
- 已创建的 K8s 资源**没有回滚机制**——例如 secret 创建成功但 storage class 创建失败时，已创建的 secret 不会被删除。
- `unload_user_pod` 中 `delete_user_pod_only` 失败时，状态保持在 STOPPING（无法回到 RUNNING），依赖心跳超时机制兜底。
- `delete_user_k8s_resources` 失败时仅影响 all_success 标志，不阻塞流程。

**ctx 改造分析**：

(1) **`update_status(CREATING)` + `update_heartbeat()` 对**（第 149-151 行）：

这是唯一一个两 DB 写之间无外部操作的场景。可以用局部 `SQL_OP_ContextData` 包裹：

```python
ctx = SQL_OP_ContextData(description="update status and heartbeat atomically")
async with ctx:
    await update_status(user_id, resolved_image, PodStatus.CREATING, ctx=ctx)
    await update_heartbeat(user_id, resolved_image, ctx=ctx)
```

改造风险极低：两个底层函数已支持 ctx，仅需调用方传入。作用域极小，不涉及任何 K8s 操作。此候选点已在 `docs/SQL_OP_refactor_plan/archive/scheduler_update_status_heartbeat_atomic.md` 中详细记录。

(2) **STOPPING → [K8s delete] → STOPPED/ERROR 序列**（unload 函数）：

**不可 ctx 包裹**。原因：
- `delete_user_pod_only` 是 K8s API 调用，耗时可能数秒至数十秒。在此期间持有 DB 事务会导致连接长期占用、锁竞争加剧。
- 即使 ctx 包裹 `update_status(STOPPING)` 和 `update_status_and_unload(STOPPED)`，`delete_user_pod_only` 仍在中间——外部操作失败后无法回滚事务，ctx 的"全或无"语义无意义。
- `STOPPING` 状态有独立的信号语义：它告诉心跳检查器和其他并发 worker "该 Pod 正在被处理"。如果在事务内设置 STOPPING，其他连接在读已提交隔离级别下看不到这个中间状态，破坏了状态机的可观测性。

(3) **create K8s 资源序列中各失败分支**：

每个 `create_*` 失败后的 `update_status(ERROR)` 都是单步 DB 写，无需 ctx。

(4) **`_wait_and_handle_ready` 中的 `update_status`**：

单步 DB 写，无需 ctx。

**结论**：**部分可改造**。仅 `create_or_start_user_pod` 中 `else` 分支的 `update_status`+`update_heartbeat` 对（第 149-151 行，两行代码）适合 ctx 包裹。该改造已有独立候选文档。其余所有 DB 写因穿插 K8s 外部操作，不可也不应纳入 ctx 事务。

---

### 2. `api/user_pod_scheduler/heartbeat_checker.py`

**当前调用链**：

```
check_and_unload_timeout_pods()
  1. query_timeout_records(threshold)              [DB 读]
  2. for each record:
       unload_user_pod(record.user_id, image=...)  [委托 scheduler，含 DB+K8s]
```

**现有补偿机制**：

- `unload_user_pod` 失败时仅记录日志，继续处理下一条记录。
- 没有对 `query_timeout_records` 的读取一致性要求。

**ctx 改造分析**：

本文件是纯编排层——`check_and_unload_timeout_pods` 自身不执行任何 DB 写操作。它读取 DB（`query_timeout_records`），然后委托 `scheduler.unload_user_pod` 执行实际的 DB+K8s 操作。

`scheduler.unload_user_pod` 的 ctx 可改造性见本报告第 1 条分析。

本文件本身无需任何 ctx 改造。

**结论**：**N/A**（本文件无直接 DB 写，无需 ctx 改造）。

---

### 3. `api/chat/schedule_pending_task.py`

**当前调用链**：

```
schedule_pending_task()
  0. RedisDistributedLock.is_locked()              [Redis 读]
  1. RedisDistributedLock.acquire()                [Redis 写（SET NX）]
  ── 锁内 ──
  2. get_branch_by_session_and_name(...)           [DB 读]
  3. get_task(branch.leaf_task_id)                 [DB 读]
  4. get_ancestors_by_leaf_task_and_statuses(...)  [DB 读]
  5. RedisEvent.wait()                             [Redis SUBSCRIBE/阻塞读]
  6. get_branch_by_session_and_name(...)           [DB 读，一致性校验]
  7. get_task(snapshot_leaf_task_id)               [DB 读，一致性校验]
  8. get_user_messages_by_session_task_id(...)     [DB 读]
  ── 锁释放 ──
  9. _process_pending_messages(...)                [异步 fire-and-forget]
```

**现有补偿机制**：

- 分布式锁保证同一 (session, branch) 只有一个调度者在运行。
- 等待父任务完成后会进行状态一致性校验（步骤 6-8），leaf_task_id、branch_id 变更或出现 user_send_message 都会放弃调度。
- 调用方取消事件（`caller_cancel_event`）和 Redis 取消事件（`schedule_pending_task_canceled`）双通道竞速取消。

**ctx 改造分析**：

本文件**没有任何 DB 写操作**。全部 6 个 DB 调用均为只读查询。Redis 操作为分布式锁和事件订阅，不涉及 DB 事务范畴。

即使 `_process_pending_messages`（在锁外异步启动）内部可能有 DB 写，那是另一个模块的职责，不在本文件范围内。

**结论**：**N/A**（纯 DB 读 + Redis，无 DB 写入可改造）。

---

### 4. `api/agent/tools/file_operations/file_hash_tracker.py`

**当前调用链**：

`record_after_edit`（第 98-102 行）：
```
1. compute_hash(content)                            [本地计算]
2. _update_snapshot_hash → update_branch_storage_snapshot(...)  [DB 写]
3. _write_to_redis → CLIENT.set(...)                [Redis 写]
```

`record_read`（第 62-69 行）：
```
1. compute_hash(content)                            [本地计算]
2. _update_snapshot_hash → update_branch_storage_snapshot(...)  [DB 写]
```

`check_external_edits`（第 104-138 行）：
```
1. get_branch_storage_snapshot(...)                 [DB 读]
2. CLIENT.mget(redis_keys)                          [Redis 读]
```

`verify_before_edit`（第 71-96 行）：
```
1. get_branch_storage_snapshot(...)                 [DB 读]
2. compute_hash(current_content)                    [本地计算]
```

**现有补偿机制**：

- `_write_to_redis` 使用 `retry_on_connection_error` 保证 Redis 写入可靠性，但不保证绝对成功。
- Redis 写入失败**不触发 DB 回滚**——设计上 Redis 是辅助存储（TTL 1 天），DB（storage_snapshot）是主体数据源。
- `check_external_edits` 通过比对 DB 和 Redis 来检测外部修改，Redis 无记录的文件不视为被修改。
- 当 Redis 不可用时，系统降级为不检测外部修改（`check_external_edits` 返回空列表）。

**ctx 改造分析**：

(1) **每次 DB 写已经是原子操作**：`_update_snapshot_hash` 通过 `update_branch_storage_snapshot` 的 `update_fn` 回调模式执行单个 DB 操作（读取 snapshot JSON 字段、修改、写回）。这是一个 DB 层面原子的 read-modify-write 操作（通过 storage_snapshot 表的单行 UPDATE），不存在多步 DB 写需要 ctx 保护。

(2) **DB+Redis 跨系统无法原子化**：`record_after_edit` 中 DB 写 → Redis 写是跨系统操作。ctx 只能管控 DB 事务，无法回滚 Redis 的 `SET`。当前设计已接受这种"尽最大努力"（best-effort）语义：DB 是事实来源（source of truth），Redis 是增强缓存，Redis 失败不影响核心功能。

(3) **不存在多步 DB 写场景**：整个类中没有一个函数需要连续执行两次或以上的 DB 写操作。

**结论**：**N/A**（每次 DB 写已是原子操作，不存在多步 DB 写需要 ctx 改造）。

---

### 5. `api/system_notification/notification_service.py`

**当前调用链**（以 `create_user_notification` 为例）：

```
create_user_notification()
  └─ write_notification_with_dual_write()
       1. insert_user_notification(data)            [DB 写，单步]
       2. write_notification_to_redis(...)           [Redis HSET]
```

其他函数的 DB 写次数：

| 函数 | DB 写次数 | 详情 |
|------|---------|------|
| `ack_system_notification` | 1 | `insert_ack`（单步 INSERT ... ON CONFLICT DO NOTHING） |
| `init_new_user_system_notifications` | 1 | `db_bulk_ack_all`（单步批量 INSERT） |
| `create_user_notification` | 1 | `insert_user_notification`（单步） |
| `ack_user_notification` | 1 | `db_soft_delete_user`（单步 UPDATE） |
| `create_session_notification` | 1 | `insert_session_notification`（单步） |
| `ack_session_notification` | 1 | `db_soft_delete_session`（单步） |
| `get_*` (3 个读函数) | 0 | cache-aside 读取模式 |

**现有补偿机制**：

- `dual_write.py` 中的 `write_notification_with_dual_write`（第 70-112 行）：先写 PG，后写 Redis。Redis 写入失败仅记录 `logfire.warning`，不触发 PG 回滚。
- `ack_with_dual_write`（第 115-138 行）：先写 PG ACK，后删 Redis。Redis 删除失败仅记日志。
- 设计原则（dual_write.py 第 3 行注释）："先写 PG（保证持久化），再写 Redis（加速读取），Redis 写入失败只记日志不回滚"。
- cache-aside 读取模式：Redis miss 时回源 PG 并回填，保证最终一致性。

**ctx 改造分析**：

该文件已在 `docs/SQL_OP_refactor_plan/archive/system_notification_and_user_pod_scheduler_no_candidates.md` 中评估过，结论为"无候选点"。本次复查确认该结论仍然成立。

核心原因：
- 每个业务函数**最多只有 1 次 DB 写操作**。不存在多步 DB 写需要 ctx 包裹。
- "双写"指的是 1 次 PG 写 + 1 次 Redis 缓存操作。Redis 不是 SQL 数据库，不适用于 `SQL_OP_ContextData` 事务机制。
- `dual_write.py` 中已通过 try/except 实现了 Redis 失败的优雅降级。

**结论**：**N/A**（每函数最多 1 次 DB 写，无需 ctx 改造）。

---

### 6. `api/system_notification_task/task_app.py`

**当前调用链**：

```
create_system_notification()
  1. insert_notification(_SystemNotificationCreate(...))  [DB 写，单步]
  2. invalidate_all_system_notification_caches()           [Redis INCR]
```

**现有补偿机制**：

- Redis 缓存失效失败时（第 44-46 行）：`logfire.error` 记录日志，**不回滚 PG 写入**。
- 代码注释（第 46 行）："依赖 TTL 兜底"——系统级公告的 Redis 缓存有 TTL，过期后自动从 PG 回填。

**ctx 改造分析**：

整个函数只有 **1 次 DB 写操作**（`insert_notification`）。随后执行的 `invalidate_all_system_notification_caches` 是 Redis 的 `INCR` 操作，不属于 DB 事务范畴。

不存在多步 DB 写需要 ctx 包裹。

**结论**：**N/A**（单次 DB 写 + Redis 操作，无需 ctx 改造）。

---

### 7. `api/human_in_loop/http_worker/router.py`

**当前调用链**：

```
hil_streaming()
  1. get_task(request_param.session_task_id)        [DB 读，权限校验]
  2. hil_msg_stream_generator(...)                   [Redis XREAD（Stream 阻塞读取）]

send_response()
  1. long_poll_worker.ack_message(...)
     ├─ CLIENT.xread(send_stream_key)               [Redis 读]
     └─ CLIENT.xdel(send_stream_key, msg_id)        [Redis 写]
  2. long_poll_worker.send_response_with_params(...)
     ├─ CLIENT.exists(recv_stream_key)              [Redis 读]
     └─ HIL_xadd_msg_with_expired(...)              [Redis XADD]

ack_notification()
  1. long_poll_worker.ack_message(...)               [Redis XREAD + XDEL]
```

**现有补偿机制**：

- `ack_message` 中 `xread` 返回空时抛 404。
- 消息未找到时抛 404。
- `send_response_with_params` 中 stream 不存在时抛 404。
- `long_poll_worker.py` 第 54 行有 TODO 注释：`# TODO: Serialize msg to postgres`——未来可能将消息持久化到 PG，但当前未实现。

**ctx 改造分析**：

本文件中唯一的 DB 操作是 `get_task`（第 57 行），这是一个**单次 DB 读**，用于权限校验（验证 session_task 存在且属于当前用户）。

所有其他操作均为纯 Redis Stream 操作（XREAD、XADD、XDEL、EXISTS）。没有任何 DB 写操作。

不存在多步 DB 写需要 ctx 包裹。

**结论**：**N/A**（仅 1 次 DB 读 + Redis Stream 操作，无 DB 写入可改造）。

---

## 总结

### 可改造的文件：0 个

没有文件存在"多个 DB 写之间无外部操作且适合 ctx 事务包裹"的完整场景。

### 部分可改造的文件：1 个

| 文件 | 可改造点 | 改造范围 |
|------|---------|---------|
| `api/user_pod_scheduler/scheduler.py` | `create_or_start_user_pod` 第 149-151 行 `update_status(CREATING)` + `update_heartbeat()` | 两行代码，用局部 ctx 包裹 |

该候选点已在独立文档 `docs/SQL_OP_refactor_plan/archive/scheduler_update_status_heartbeat_atomic.md` 中详细记录，包括伪代码、注意事项和风险评估。

### 不可改造的文件：6 个

| 文件 | 不可改造原因 |
|------|------------|
| `heartbeat_checker.py` | 纯编排层，无直接 DB 写 |
| `schedule_pending_task.py` | 纯 DB 读 + Redis，无 DB 写 |
| `file_hash_tracker.py` | 每次 DB 写已是原子操作（单步 update_branch_storage_snapshot），无多步 DB 写 |
| `notification_service.py` | 每函数最多 1 次 DB 写，无多步 DB 写 |
| `task_app.py` | 单次 DB 写 + Redis 操作 |
| `router.py` (HIL) | 仅 1 次 DB 读（权限校验），无 DB 写 |

### 核心发现

本次分析覆盖的 7 个文件虽然都涉及"DB 与其他系统穿插"，但绝大多数是以下两种模式：

1. **DB 写 + 外部操作**（K8s、Redis）：DB 写入之间夹着不可回滚的外部操作，ctx 事务的"全或无"语义在这些场景中不适用。典型如 scheduler.py 的 `STOPPING → K8s delete → STOPPED` 序列。

2. **DB 读 + 外部操作**：文件的核心逻辑是外部系统操作（Redis Stream、Redis Lock/Event），DB 仅承担少量读取（权限校验、状态检查）。这些文件根本没有需要 ctx 包裹的 DB 写。

真正存在"连续多步 DB 写且之间无外部操作"的只有 scheduler.py 的两行代码（`update_status` + `update_heartbeat`），且已在之前的分析中识别为低优先级候选点。

### 设计层面的观察

这些文件的架构揭示了一个模式：当业务逻辑需要跨系统协调时（DB + K8s / DB + Redis），系统选择了 **"DB 作为状态机记录，外部系统作为实际操作执行者"** 的设计。这种设计中：

- DB 状态（CREATING、STOPPING、RUNNING、ERROR 等）反映了外部操作的**期望目标**或**实际结果**，而非与外部操作形成 ACID 事务。
- 中间状态（如 STOPPING）具有**信号语义**——向其他系统组件传达意图。
- 补偿机制依赖于**状态驱动的重试/超时**（如心跳超时自动卸载），而非事务回滚。

这种设计是正确的——跨系统的分布式操作本质上无法用单数据库事务保证原子性，强行用 ctx 包裹只会引入长事务、降低可观测性、且无实际收益。
