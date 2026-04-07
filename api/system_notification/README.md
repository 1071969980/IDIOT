# App Notification 模块

应用内通知系统，支持三级通知：系统级、用户级、会话级。采用 PG + Redis 双写 + Cache-Aside 缓存策略，独立部署为 FastAPI 微服务。

## 目录结构

```
api/system_notification/
├── notification_service.py          # 服务编排层
├── dual_write.py                    # 双写策略层（PG + Redis 协调）
├── redis_ops.py                     # Redis 缓存操作
├── types.py                         # 跨层统一类型 InternalNotification
├── sql_stat/                        # PG 数据层
│   ├── system_notification/         #   系统级公告表
│   ├── system_notification_ack/     #   系统级 ACK 记录表
│   ├── user_notification/           #   用户级公告表
│   └── session_notification/        #   会话级公告表

api/app/system_notification/         # HTTP API 层
├── system_notification_app.py       #   FastAPI 应用入口
├── endpoints.py                     #   端点实现
├── data_model.py                    #   Pydantic 请求/响应模型
└── router_declare.py                #   路由声明

api/system_notification_task/        # Task Pod（系统公告创建）
└── task_app.py                      #   CLI 入口，一次性 Job
```

## 架构分层

```
┌─────────────────────────────────────────────────────────────────┐
│  部署层: K8s Deployment + CronJob + Nginx 反向代理               │
├─────────────────────────────────────────────────────────────────┤
│  HTTP API 层 (api/app/system_notification/)                     │
│  FastAPI 端点，认证，Pydantic 模型                               │
├─────────────────────────────────────────────────────────────────┤
│  服务编排层 (notification_service.py)                            │
│  三级通知的业务函数，协调 dual_write 和 sql_stat                  │
├─────────────────────────────────────────────────────────────────┤
│  双写策略层 (dual_write.py)                                      │
│  write / ack / read 三个通用策略函数                              │
├──────────────┬──────────────────────────────────────────────────┤
│  Redis 缓存层 │  PG 数据层 (sql_stat/)                           │
│ (redis_ops)  │  每个 SQL 文件 + utils.py 一对                    │
└──────────────┴──────────────────────────────────────────────────┘
```

## 类型流转

跨层使用统一的 `InternalNotification` dataclass，保证类型安全：

```
SQL dataclass          dual_write            notification_service     endpoints
─────────────────  →  ────────────────  →  ────────────────────  →  ──────────────
_SystemNotificationResult  _dataclass_to_internal()  list[InternalNotification]  _to_item()
_UserNotificationResult    _dict_to_internal()                                 NotificationItem
_SessionNotificationResult           InternalNotification (全程)
```

- `types.py` 定义 `InternalNotification`，所有中间层函数签名使用它
- Endpoint 层通过 `_to_item()` 转为 Pydantic `NotificationItem` 返回给客户端
- Redis 缓存的 dict 通过 `_dict_to_internal()` 还原为 `InternalNotification`

## 数据库层 (sql_stat/)

### 四张表

| 表 | 用途 | 消费方式 |
|---|---|---|
| `system_notifications` | 全局广播公告，无 user_id | ACK 确认（fan-out on read） |
| `system_notification_acks` | 用户 ACK 记录，UNIQUE(notification_id, user_id) | ON CONFLICT DO NOTHING 幂等 |
| `user_notifications` | 定向投放给特定用户 | 软删除 (deleted_at) |
| `session_notifications` | 投放到特定会话 | 软删除 (deleted_at) |

### 外键约束

所有 user_id 和 session_id 均设有外键引用，`ON DELETE CASCADE`：
- `user_notifications.user_id` → `simple_users(id)`
- `session_notifications.session_id` → `u2a_sessions(id)`
- `session_notifications.user_id` → `simple_users(id)`
- `system_notification_acks.user_id` → `simple_users(id)`

### 系统级公告的读取查询

使用 `NOT EXISTS` 子查询获取用户未 ACK 的公告，配合 `(user_id, notification_id)` 复合索引走索引定位：

```sql
SELECT sn.id, sn.level, sn.content, sn.created_at, sn.updated_at
FROM system_notifications sn
WHERE NOT EXISTS (
    SELECT 1 FROM system_notification_acks sna
    WHERE sna.notification_id = sn.id AND sna.user_id = :user_id
)
ORDER BY sn.created_at DESC;
```

## Redis 缓存层 (redis_ops.py)

### 数据结构

使用 Redis Hash 存储通知缓存，`notification_id` 作为 field，JSON 数据作为 value：

```
hash_key: sys_notif:user:<uuid>
  ├── <notification_id>  →  {"id":"...","level":"High","content":"...","created_at":"..."}
  ├── <notification_id>  →  {"id":"...","level":"Normal","content":"...","created_at":"..."}
  └── _version           →  "42"   (仅系统级使用)
```

选择 Hash 而非 Stream/List 的原因：需要按 notification_id 做 O(1) 单条删除（ACK 时）。

### Key 命名

```python
SYS_NOTIF_PREFIX     = "sys_notif:user:"       # 系统级，按用户维度
USER_NOTIF_PREFIX    = "user_notif:user:"       # 用户级
SESSION_NOTIF_PREFIX = "session_notif:session:" # 会话级
```

TTL 默认 7 天。

### 全局版本号机制（系统级公告专用）

系统级公告的缓存失效采用全局版本号，替代 `SCAN + UNLINK` 全量删除：

- 创建公告时：`INCR sys_notif:version`（O(1)），所有用户缓存瞬间失效
- 读取时：比对 Hash 内 `_version` 与全局版本号，不匹配则回源 PG
- 版本号存在 Hash 的 `_version` field 中（元数据，非公告数据）

### 空 Marker（防缓存穿透）

PG 查询结果为空时设置 marker key `{hash_key}:empty`，防止反复穿透到 PG。

- 系统级：marker 值为版本号字符串，新公告创建后旧 marker 自动失效（版本不匹配）
- 用户/会话级：marker 值为 `"1"`，仅检查 key 是否存在

## 双写策略层 (dual_write.py)

三个通用函数，封装"先 PG 后 Redis"的一致性策略：

### `write_notification_with_dual_write`

写入流程：PG 写入 → 构造 Redis 数据 → 写入 Redis（失败仅 warning 不回滚）。

Redis 数据从 PG 返回的 result 对象自动构造，保证与 PG 数据一致（包括数据库生成的 UUID 和时间戳）。

### `ack_with_dual_write`

ACK 流程：PG 确认（ACK 记录 / 软删除） → 从 Redis 删除 → 检查 Hash 是否为空 → 设 empty marker。

上层通过 lambda 传入具体的 PG 操作，因为系统级、用户级、会话级的 PG 操作不同，但双写策略相同。

### `read_with_cache_fallback`

读取流程，分两条路径：

**系统级（带版本号）**：
1. 获取全局版本号
2. 检查空 marker（带版本号比对）
3. 比对缓存版本号 → 匹配则信任缓存
4. 不匹配 → 回源 PG → pipeline 批量回填 Redis → 写入版本号

**用户/会话级（传统 cache-aside）**：
1. 检查空 marker
2. 读 Redis → 有数据则返回
3. 回源 PG → pipeline 批量回填 Redis

Redis 回填使用 pipeline 批量写入，减少网络往返。

## 服务编排层 (notification_service.py)

胶水层，把 SQL 操作和 Redis 操作通过 dual_write 组装成业务函数。

### 系统级（无创建，由 Task Pod 负责）

| 函数 | 说明 |
|---|---|
| `get_unacked_system_notifications(user_id)` | cache-aside 读取未 ACK 公告 |
| `ack_system_notification(notification_id, user_id)` | PG ACK + 删 Redis，幂等 |

### 用户级

| 函数 | 说明 |
|---|---|
| `create_user_notification(user_id, level, content)` | 双写创建 |
| `get_user_notifications(user_id)` | cache-aside 读取 |
| `ack_user_notification(notification_id, user_id)` | PG 软删除 + 删 Redis |

### 会话级

| 函数 | 说明 |
|---|---|
| `create_session_notification(session_id, user_id, level, content)` | 双写创建 |
| `get_session_notifications(session_id, user_id)` | cache-aside 读取，带 user_id 权限校验 |
| `ack_session_notification(notification_id, session_id)` | PG 软删除 + 删 Redis |

会话级函数只需 `session_id` 参数定位（session_id 已关联唯一 user_id）。

## HTTP API 层

### 应用入口

独立 FastAPI 应用，root_path 为 `/app-notification`，与主 API 分开部署。端口 8001。

生命周期：分布式锁保护建表 → init_logger → graceful shutdown。

CORS 由 Nginx 统一处理（`proxy_cors.inc`），应用层不添加 CORS 中间件。

### 端点

所有端点需认证（`get_current_active_user`）。

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/notifications/system-notifications` | 获取未确认系统公告 |
| POST | `/notifications/system-notifications/{id}/ack` | 确认系统公告 |
| GET | `/notifications/user-notifications` | 获取用户级公告 |
| POST | `/notifications/user-notifications/{id}/ack` | 确认用户级公告 |
| GET | `/notifications/session-notifications/{session_id}` | 获取会话级公告 |
| POST | `/notifications/session-notifications/{session_id}/{id}/ack` | 确认会话级公告 |

对外完整路径示例：`/app-notification/notifications/system-notifications`

### 分页

所有 GET 端点支持可选的 `PaginationParams`（`limit` / `offset`），默认不启用（返回全部）。

### 请求路径解析

```
客户端: GET /app-notification/notifications/system-notifications
  → Nginx (location /app-notification/) 原样转发
  → FastAPI root_path="/app-notification" 剥离
  → router prefix="/notifications" 匹配
  → endpoint "/system-notifications" 命中
```

注意：Nginx `proxy_pass` 末尾不带 `/`，确保路径原样转发。

## Task Pod (system_notification_task/)

一次性 CLI 工具，不启动 FastAPI，通过 K8s Job 手动触发：

```bash
python -m api.system_notification_task.task_app --level High --content "系统将于今晚22:00维护"
```

流程：PG 写入公告 → `INCR` 全局版本号 → 打印 notification_id 退出。

缓存失效失败不回滚 PG 写入，依赖 7 天 TTL 兜底。

## 部署 (k8s/)

| 资源 | 文件 | 说明 |
|---|---|---|
| Deployment + Service | `12.2-system-notification-api.yaml` | 通知 API 服务，单副本，8001 端口 |
| CronJob | `12.3-system-notification-task.yaml` | 系统公告创建任务模板，手动触发 |
| Nginx location | `13-nginx.yaml` + `proxy_cors.inc` | 反向代理 + CORS |

CronJob 使用 `schedule: "0 0 31 2 *"`（不存在的日期）+ `suspend: true` 双重保护，仅作为手动触发的模板：

```bash
kubectl create job manual-notif-$(date +%s) \
    --from=cronjob/system-notification-task -- \
    --level High --content "维护公告"
```

Nginx 的 CORS + proxy 头配置抽成 `proxy_cors.inc`，新增 location 时只需 `include`。
