# 候选：create_or_start_user_pod 中 update_status + update_heartbeat 原子化

**状态**: 待审查
**发现日期**: 2026-07-12
**优先级建议**: P2

## 涉及文件

- `api/user_pod_scheduler/scheduler.py` — `create_or_start_user_pod` 函数，第 150-151 行
- `api/user_pod_scheduler/sql_stat/utils.py` — `update_status`、`update_heartbeat` 均已 ctx 改造（无需修改）

## 当前调用链

```
create_or_start_user_pod(user_id, image)
  │
  ├─ query_record_by_user_id_and_image(...)          [纯读]
  │
  ├─ 分支判断：existing_record?
  │   ├─ 否 → insert_record(...)                     [独立 commit，单个写操作，无需改造]
  │   └─ 是 → update_status(CREATING)                [独立 commit]
  │          update_heartbeat(...)                    [独立 commit]
  │
  ├─ 创建 K8S 资源（JuiceFS secret / SC / PVC）       [跨系统，不在本次改造范围]
  │   └─ 各步骤失败时 update_status(ERROR, ...)       [独立 commit，单步]
  │
  ├─ create_user_pod(...)                            [K8s，跨系统]
  │
  └─ _wait_and_handle_ready(...)                     [内部 update_status(RUNNING)，独立 commit]
```

## 当前风险

在 `existing_record` 分支（第 149-151 行）中：

```python
else:
    await update_status(user_id, resolved_image, PodStatus.CREATING)
    await update_heartbeat(user_id, resolved_image)
```

两个 DB 写操作各自独立 commit。如果 `update_status` 成功但 `update_heartbeat` 失败（例如网络闪断、连接池耗尽），会造成：

- DB 中记录状态已经是 `CREATING`，但 `heartbeat_at` 仍为旧值
- 如果 `heartbeat_at` 恰好已超时，心跳检查器 `heartbeat_checker.py` 可能将该记录标记为超时并触发卸载
- 后续 K8s Pod 创建流程仍在进行，卸载操作与创建操作产生竞争

**风险等级**：低。两个操作间隔极短（同进程内的两次 async DB 调用），同时失败的概率很低。

## 改造方案

在 `else` 分支中创建局部 `SQL_OP_ContextData`，将 `update_status` 和 `update_heartbeat` 纳入同一个事务。两个底层函数均已支持 `ctx` 参数，无需修改。

### ctx 创建位置

在 `create_or_start_user_pod` 函数中，`else` 分支内部创建 `ctx`，仅包裹这两行。

### ctx 作用域

仅覆盖步骤 3 的 `else` 分支中的两个 DB 写操作。不扩展到后续的 K8s 操作——因为 K8s 操作不是 DB 事务，且跨系统不适合纳入 SQL 事务。

### 异常处理

`async with ctx:` 块内任一操作失败（抛异常），ctx 自动 rollback，两个写入都不会持久化。上层已有 try/except（第 208 行），异常会被捕获并统一处理为 `update_status(ERROR, str(e))`。

## 伪代码

### 改造前

```python
# 3. 创建数据库记录（状态：creating）
if not existing_record:
    await insert_record(_UserPodRecordCreate(
        user_id=user_id,
        status=PodStatus.CREATING,
        pod_name=pod_name,
        image=resolved_image,
    ))
else:
    await update_status(user_id, resolved_image, PodStatus.CREATING)
    await update_heartbeat(user_id, resolved_image)
```

### 改造后

```python
from api.sql_utils.utils import SQL_OP_ContextData

# 3. 创建数据库记录（状态：creating）
if not existing_record:
    await insert_record(_UserPodRecordCreate(
        user_id=user_id,
        status=PodStatus.CREATING,
        pod_name=pod_name,
        image=resolved_image,
    ))
else:
    ctx = SQL_OP_ContextData()
    async with ctx:
        await update_status(user_id, resolved_image, PodStatus.CREATING, ctx=ctx)
        await update_heartbeat(user_id, resolved_image, ctx=ctx)
```

## 注意事项

1. **作用域极小**：ctx 仅包裹两行代码，不涉及 K8s 操作或后续流程。改造量极小，风险低。

2. **不需要透传**：`update_status` 和 `update_heartbeat` 已支持 `ctx` 参数，仅需调用方传入 `ctx=ctx`。

3. **不影响 `if` 分支**：`insert_record` 是单步写入，不需要 ctx 包裹。如果未来需要将此分支也纳入事务（例如 create + K8s 失败回滚），那是更大范围的改造，需要将 ctx 作用域扩展到覆盖 K8s 操作，这在当前架构下不可行（K8s 操作不可回滚）。

4. **与现有异常处理兼容**：函数外层（第 208-219 行）已有 `except Exception as e:` 统一错误处理，ctx 内的异常会先被 `async with ctx:` 捕获并 rollback，然后继续向上抛出，最终被外层 except 处理。行为与改造前一致——区别在于 rollback 保证了两个写入都不会残留。

5. **改造价值有限**：两个操作之间没有网络 I/O 或耗时操作，同时失败概率极低。建议作为低优先级清理项，不阻塞其他高价值候选点。
