# 评估：system_notification 与 user_pod_scheduler 模块 — 无合适候选点

**状态**: 已归档
**发现日期**: 2026-07-12
**优先级建议**: N/A（无候选点）

## 评估范围

对以下两个 FastAPI 应用入口文件及其对应的业务逻辑层进行了完整审查：

1. `api/app/system_notification_app.py` — 系统通知模块
2. `api/app/user_pod_scheduler_app.py` — Pod 调度器模块

## 结论

**两个 app 文件本身均为 FastAPI 引导文件（lifespan 管理 + init_db + router 注册），不含任何业务逻辑级别的 DB 写操作。** 向下追溯到业务逻辑层后，两个模块均不存在 "多步 DB 写操作各自独立 commit 且应当合并为原子事务" 的场景。

---

## 模块一：system_notification（系统通知）

### app 文件分析

`api/app/system_notification_app.py` 内容：
- `init_db()`：依次调用 4 个 `create_table()`（`CREATE TABLE IF NOT EXISTS`），DDL 操作各自独立执行，建表是幂等操作，无需事务原子性
- `lifespan()`：启动时初始化，不处理业务请求
- 路由器注册

**结论：app 文件本身无候选点。**

### 业务逻辑层分析

实际业务代码位于以下文件：
- `api/system_notification/notification_service.py` — 服务层，9 个函数
- `api/system_notification/dual_write.py` — PG+Redis 双写协调层

逐个函数审查结果：

| 函数 | PG 写操作数 | 分析 |
|------|-----------|------|
| `get_unacked_system_notifications` | 0（纯读） | cache-aside 读取模式 |
| `ack_system_notification` | 1（`insert_ack`） | 单次 PG 写 + Redis 删除 |
| `init_new_user_system_notifications` | 1（`db_bulk_ack_all`） | 单次 PG 批量插入 |
| `create_user_notification` | 1（`insert_user_notification`） | 单次 PG 写 + Redis 写 |
| `get_user_notifications` | 0（纯读） | cache-aside 读取模式 |
| `ack_user_notification` | 1（`db_soft_delete_user`） | 单次 PG 软删除 + Redis 删除 |
| `create_session_notification` | 1（`insert_session_notification`） | 单次 PG 写 + Redis 写 |
| `get_session_notifications` | 0（纯读） | cache-aside 读取模式 |
| `ack_session_notification` | 1（`db_soft_delete_session`） | 单次 PG 软删除 + Redis 删除 |

**每个函数最多只有 1 次 PG 写操作。** 所谓 "双写" 是 PG 写 + Redis 缓存操作，Redis 不是 SQL 数据库，不适用 `SQL_OP_ContextData` 事务机制。

**结论：通知模块无多步 DB 写候选点。**

---

## 模块二：user_pod_scheduler（Pod 调度器）

### app 文件分析

`api/app/user_pod_scheduler_app.py` 内容：
- `init_db()`：调用 1 个 `create_table()`，单次 DDL 操作
- `lifespan()`：初始化 DB、日志、worker pool、心跳检测器
- 路由器注册

**结论：app 文件本身无候选点。**

### 业务逻辑层分析

实际业务代码位于以下文件：
- `api/user_pod_scheduler/scheduler.py` — 核心调度逻辑，5 个函数
- `api/user_pod_scheduler/heartbeat_checker.py` — 心跳检测定时任务

#### 存在多步 DB 写的函数

**`unload_user_pod`（scheduler.py:263-303）**：

```
update_status(STOPPING)     ← PG 写 #1 (独立 commit)
delete_user_pod_only()      ← K8S 外部操作
update_status_and_unload(STOPPED)  ← PG 写 #2 (成功时, 独立 commit)
或 update_status(ERROR)     ← PG 写 #2 (失败时, 独立 commit)
```

**`unload_all_user_pods`（scheduler.py:310-337）**：

```
for each record:
    update_status(STOPPING)         ← PG 写 (独立 commit)
    delete_user_pod_only()          ← K8S 外部操作
    update_status_and_unload(STOPPED) 或 update_status(ERROR)  ← PG 写 (独立 commit)
delete_user_k8s_resources()         ← K8S 外部操作
```

**`create_or_start_user_pod`（scheduler.py:90-219）else 分支**：

```
update_status(CREATING)     ← PG 写 #1 (独立 commit)
update_heartbeat()          ← PG 写 #2 (独立 commit)
```

#### 不适合合并为事务的原因

1. **外部操作穿插**：所有多步 DB 写之间都夹着 K8S API 调用（`delete_user_pod_only`、`create_juicefs_secret`、`create_storage_class`、`create_pvc`、`create_user_pod`）。K8S 操作不属于 DB 事务范畴，无法回滚。在不回滚 K8S 的前提下，DB 事务的 "全或无" 语义失效。

2. **中间状态有独立语义**：
   - `STOPPING` 状态向心跳检测器和其他 worker 信号：该 Pod 正在被卸载中，请勿重复操作
   - `CREATING` 状态同样有信号作用
   - 将 STOPPING → STOPPED 合并在同一事务内，会使得 `STOPPING` 状态对其他 worker 不可见（仅当前事务可见），破坏了状态机的可观测性

3. **状态机本质**：这些函数本质上是在驱动一个跨系统的状态机（DB 状态 + K8S 资源状态），每个 `update_status` 调用都是状态机的一次合法转移，而非一个需要原子性的业务操作拆分。

**结论：Pod 调度器模块存在多步 DB 写，但不应合并为事务。**

---

## 总结

| 模块 | app 文件有业务逻辑 | 业务层有多步 DB 写 | 适合事务改造 | 原因 |
|------|-------------------|-------------------|-------------|------|
| system_notification | 否（纯引导） | 否（每函数最多 1 次 PG 写） | 否 | 无多步 PG 写操作 |
| user_pod_scheduler | 否（纯引导） | 是（2-3 次 PG 写） | 否 | DB 写之间穿插不可回滚的外部操作，中间状态有独立语义 |

**两个模块均无可推进的业务层候选点。**
