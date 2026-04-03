---
文档标题：system_notification_spec_design
文档描述：系统公告功能的需求定义、概念设计、数据存储设计、API设计和执行逻辑。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

# 系统公告功能设计文档

## 目录

- [概念定义](#概念定义)
- [设计结构与执行逻辑](#设计结构与执行逻辑)
  - [整体架构](#整体架构)
  - [双存储协同机制](#双存储协同机制)
  - [三类公告的生命周期](#三类公告的生命周期)
- [数据存储设计](#数据存储设计)
  - [PostgreSQL 表设计](#postgresql-表设计)
  - [Redis Stream 设计](#redis-stream-设计)
- [API 设计](#api-设计)
  - [读取接口](#读取接口)
  - [ACK 与删除接口](#ack-与删除接口)
  - [管理写入接口](#管理写入接口)
- [文件结构](#文件结构)

---

## 概念定义

**公告（Notification）**：由系统或管理员向用户推送的消息，用于传达系统运维信息、用户级别提醒或会话级别提示。公告区别于实时聊天消息，是单向的信息广播。

**系统级公告（SystemNotification）**：面向全体用户的广播消息。每条公告独立存在，用户需逐条确认（ACK）。一条公告可被多个用户确认，因此公告与确认记录是一对多关系。

**用户级公告（UserNotification）**：面向特定用户的消息。公告绑定到指定用户，用户删除该公告即视为确认（ACK）。采用软删除机制。

**会话级公告（SessionNotification）**：面向特定会话中用户的消息。公告绑定到指定会话与用户，用户删除该公告即视为确认（ACK）。采用软删除机制。

**ACK（Acknowledgement）**：用户对公告的确认动作。系统级公告通过显式 ACK 接口确认；用户级和会话级公告通过删除操作确认。

**双写（Dual Write）**：用户级和会话级公告的写入操作同时写入 Redis 和 PostgreSQL，保证两个存储的数据一致性。系统级公告不使用创建时双写，而是仅写入 PostgreSQL，Redis 缓存通过按需回填机制填充。

**回填（Backfill）**：当 Redis 缓存未命中时，从 PostgreSQL 读取数据并写入 Redis，以填充缺失的缓存数据。

**缓存清理（Cache Invalidation）**：系统级公告创建后，由 task pod 异步清理所有用户的系统级公告 Redis 缓存，确保下次读取时从数据库拉取最新数据。

**软删除（Soft Delete）**：通过设置 `deleted_at` 字段标记记录为已删除，而非物理删除数据行。

## 设计结构与执行逻辑

### 整体架构

系统公告功能作为独立模块运行，与主应用解耦：

1. **独立 FastAPI 应用**：公告功能拥有独立的 FastAPI 应用进程，负责处理公告的读取和 ACK 请求。这与项目中已有的 User Pod Scheduler 模式一致（参见 `api/app/user_pod_scheduler_app.py`）。
2. **独立 Task Pod**：系统级公告的创建由独立的 Task Pod 负责（写 DB + 清理 Redis 缓存），与读取服务解耦。用户级和会话级公告由主应用服务层直接写入。
3. **独立存储空间**：公告数据使用独立的 Redis Stream 和 PostgreSQL 表，不与主业务数据混用。
4. **服务层调用**：主应用通过 Python 函数直接调用公告服务层（`notification_service.py`）写入用户级和会话级公告，不需要经过 HTTP 接口。

### 双存储协同机制

公告数据同时存储在 Redis 和 PostgreSQL 中，两者各司其职：

- **Redis**：作为读取优先层，提供低延迟的公告查询。使用 Redis Stream 数据结构，每条 Stream 消息对应一条公告记录。
- **PostgreSQL**：作为持久化层，保证数据不丢失，并支持复杂的查询需求（如按时间范围筛选、按状态统计等）。

**写入流程**：

系统级公告与用户级/会话级公告的写入策略不同：

- **用户级/会话级公告（双写）**：
  1. 接收写入请求。
  2. 将公告数据写入 PostgreSQL，获取生成的 UUID。
  3. 将公告数据以该 UUID 为消息 ID 写入对应的 Redis Stream。
  4. 若 Redis 写入失败，记录错误日志但不回滚 PostgreSQL，由后续回填机制修复。

- **系统级公告（只写 DB + 清缓存）**：
  1. Task Pod 接收写入请求。
  2. 将公告数据写入 PostgreSQL `system_notifications` 表，获取生成的 UUID。
  3. 异步清理所有用户的系统级公告 Redis 缓存（`SCAN MATCH sys_notif:user:*` + `UNLINK`），确保各用户下次读取时从数据库拉取最新数据。

**读取流程（Redis 优先 + 回填）**：

1. 接收读取请求，先从 Redis Stream 读取。
2. 若 Redis 读取成功，直接返回数据。
3. 若 Redis 读取失败（Key 不存在、连接异常等），从 PostgreSQL 读取。
4. 将 PostgreSQL 读取到的数据回填到 Redis Stream，并设置 TTL。
5. 返回数据。

### 三类公告的生命周期

**系统级公告生命周期**：

1. 管理员通过 Task Pod 创建公告，写入 PG `system_notifications` 表，然后清理所有用户的系统级公告 Redis 缓存（`sys_notif:user:*`）。
2. 用户调用读取接口时，若 Redis 缓存已被清理（cache miss），则从 PG 查询 `system_notifications` 表并排除 `system_notification_acks` 中该用户已确认的记录，回填至 Redis 缓存。
3. 用户对公告调用 ACK 接口，先在 PG `system_notification_acks` 表插入确认记录，再从 Redis 缓存中删除该消息。
4. 已 ACK 的公告不再出现在该用户的未读列表中。

**用户级公告生命周期**：

1. 管理员为指定用户创建公告，双写到 PG `user_notifications` 表和 Redis `user_notif:user:{user_uuid}` Stream。
2. 用户登录后调用读取接口，获取自己的用户级公告。
3. 用户删除公告（即 ACK），双写到 PG（软删除）和 Redis（从 Stream 中移除或标记）。
4. 已删除的公告不再出现。

**会话级公告生命周期**：

1. 管理员为指定会话创建公告，双写到 PG `session_notifications` 表和 Redis `session_notif:session:{session_uuid}` Stream。由于 `session_id` 已关联唯一用户，无需额外传入 `user_id`。
2. 会话用户调用读取接口，获取该会话的公告。
3. 用户删除公告（即 ACK），双写到 PG（软删除）和 Redis（从 Stream 中移除）。
4. 已删除的公告不再出现。

## 数据存储设计

### PostgreSQL 表设计

所有表遵循项目已有的 SQL 规范：使用 `uuidv7()` 作为主键默认值，包含 `created_at` 和 `updated_at` 时间戳字段。SQL 模板文件参考项目中已有的模式（如 `api/user_space/file_system/sql_stat/FileSystem.sql`），使用命名参数格式（`:param_name`）。

**`system_notifications` 表**：

存储系统级公告的主体内容，每条记录代表一条面向全体用户的公告。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK DEFAULT uuidv7() | 公告唯一标识 |
| level | TEXT | 公告级别（如 info、warning、critical） |
| content | TEXT | 公告正文内容 |
| created_at | TIMESTAMPTZ DEFAULT NOW() | 创建时间 |
| updated_at | TIMESTAMPTZ DEFAULT NOW() | 更新时间 |

需要 `updated_at` 自动更新触发器，与 `user_file_system` 表的模式一致。

**`system_notification_acks` 表**：

存储用户对系统级公告的确认记录。每条记录代表一个用户对一条公告的 ACK。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK DEFAULT uuidv7() | 确认记录唯一标识 |
| notification_id | UUID FK | 关联 system_notifications.id |
| user_id | UUID | 确认该公告的用户 |
| acked_at | TIMESTAMPTZ DEFAULT NOW() | 确认时间 |

需要联合唯一索引 `(notification_id, user_id)` 防止重复 ACK。

**`user_notifications` 表**：

存储用户级公告，每条记录绑定一个用户。通过 `deleted_at` 实现软删除。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK DEFAULT uuidv7() | 公告唯一标识 |
| user_id | UUID | 目标用户 |
| level | TEXT | 公告级别 |
| content | TEXT | 公告正文内容 |
| created_at | TIMESTAMPTZ DEFAULT NOW() | 创建时间 |
| updated_at | TIMESTAMPTZ DEFAULT NOW() | 更新时间 |
| deleted_at | TIMESTAMPTZ NULLABLE | 软删除时间（删除即 ACK） |

需要 `updated_at` 自动更新触发器。需要 `user_id` 索引和 `deleted_at IS NULL` 的部分索引以提高查询效率。

**`session_notifications` 表**：

存储会话级公告，每条记录绑定一个会话和一个用户。**注意**：在当前系统中，一个 `session_id` 已唯一对应一个 `user_id`，因此 SQL 查询和 Redis Key 仅按 `session_id` 维度操作，无需额外传入 `user_id` 参数。通过 `deleted_at` 实现软删除。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK DEFAULT uuidv7() | 公告唯一标识 |
| session_id | UUID | 目标会话 |
| user_id | UUID | 目标用户 |
| level | TEXT | 公告级别 |
| content | TEXT | 公告正文内容 |
| created_at | TIMESTAMPTZ DEFAULT NOW() | 创建时间 |
| updated_at | TIMESTAMPTZ DEFAULT NOW() | 更新时间 |
| deleted_at | TIMESTAMPTZ NULLABLE | 软删除时间（删除即 ACK） |

需要 `updated_at` 自动更新触发器。需要 `(session_id)` 索引和 `deleted_at IS NULL` 的部分索引。由于 `session_id` 已关联唯一用户，无需 `(session_id, user_id)` 联合索引。

### Redis Stream 设计

Redis 使用 Stream 数据结构存储公告，Key 命名遵循以下规范：

| Key 模式 | 用途 |
|----------|------|
| `sys_notif:user:{user_uuid}` | 指定用户的系统级公告 Stream |
| `user_notif:user:{user_uuid}` | 指定用户的用户级公告 Stream |
| `session_notif:session:{session_uuid}` | 指定会话的会话级公告 Stream（session_id 已关联唯一用户，无需 user_id 维度） |

**Stream 消息结构**：

- **entry ID**：由 Redis 自动生成（`<milliseconds>-<sequence>` 格式），遵循项目已有模式（参见 [Stream操作](./system_notification_spec_context.md#22-stream操作)）。
- **消息体（fields）**：包含 `notification_id`（UUID 字符串，与 PG 记录关联）和 `data`（JSON 序列化的完整公告数据）。
- **TTL**：所有 Stream Key 设置 TTL（默认 7 天），防止缓存清理失败时的长期脏数据。

**空结果标记 Key**：

为防止缓存穿透（用户 ACK 所有公告后 PG 返回空列表导致每次查询穿透到 PG），引入标记 Key 机制：

| Key 模式 | 用途 |
|----------|------|
| `{stream_key}:empty` | 标记该 Stream 对应的数据为空（无未读公告） |

- PG 查询返回空列表时，设置标记 Key（TTL 与 Stream 相同）
- 读取时先检查标记 Key，若存在则直接返回空列表，不查询 PG
- 缓存清理时同时清理标记 Key，确保新公告创建后用户能重新从 PG 拉取

**系统级公告的缓存策略**：

系统级公告不维护 `acked_users` 字段。Redis Stream `sys_notif:user:{user_uuid}` 仅缓存该用户的**未 ACK 公告列表**。当用户 ACK 一条公告时，仅通过 `XDEL` 删除 Stream 中匹配 `notification_id` 的单条消息，不移除整个 Stream Key——剩余未 ACK 的公告仍在缓存中。只有创建新系统级公告时才会通过 `invalidate_all_system_notification_caches` 清空所有用户的整个 Stream（含标记 Key）。缓存整体失效后由读取流程从 PG 重新拉取并回填。

## API 设计

公告 API 作为独立 FastAPI 应用提供，应用结构与项目中 User Pod Scheduler 应用（`api/app/user_pod_scheduler_app.py`）保持一致。

**路由与反向代理**：`root_path` 用于反向代理路径前缀（影响 OpenAPI 文档和 URL 生成），`APIRouter` 的 `prefix` 定义应用内部路由前缀。两者职责不同，不应重复：`root_path="/system-notification"` 对应 Nginx 转发路径，`APIRouter(prefix="/notifications")` 定义应用内部路由分组。Nginx 将 `/system-notification/*` 路径的请求转发到公告服务端口，FastAPI 根据 `root_path` 生成正确的 OpenAPI 文档和 URL。

### 读取接口

**`GET /system-notifications`**

获取当前登录用户未 ACK 的系统级公告列表。采用 cache-aside 模式：先从 Redis Stream `sys_notif:user:{user_uuid}` 读取（缓存中仅包含未 ACK 的公告）；若缓存 miss（Key 不存在或已过期），则从 PG 查询 `system_notifications` 表并排除 `system_notification_acks` 中该用户已确认的记录，然后回填 Redis 并设置 TTL。

请求参数：无（通过认证中间件获取 user_id）

响应体：

```json
{
  "notifications": [
    {
      "id": "uuid",
      "level": "warning",
      "content": "公告内容",
      "created_at": "2026-01-01T00:00:00Z"
    }
  ]
}
```

**`GET /user-notifications`**

获取当前登录用户的未删除用户级公告。优先从 Redis Stream `user_notif:user:{user_uuid}` 读取；若失败则从 PG 查询 `user_notifications` 表（`deleted_at IS NULL`），然后回填 Redis。

响应格式与系统级公告一致。

**`GET /session-notifications/{session_uuid}`**

获取指定会话的未删除会话级公告。优先从 Redis Stream `session_notif:session:{session_uuid}` 读取；若失败则从 PG 查询 `session_notifications` 表（`session_id` 匹配且 `deleted_at IS NULL`），然后回填 Redis。

路径参数：`session_uuid` — 会话 ID

响应格式与系统级公告一致。

### ACK 与删除接口

**`POST /system-notifications/{notification_uuid}/ack`**

确认系统级公告。先在 PG `system_notification_acks` 表插入确认记录（`ON CONFLICT DO NOTHING` 保证幂等），再从 Redis Stream 中按 `notification_id` 匹配并删除该消息。重复 ACK 返回 `already_acked` 而非报错。PG ACK 为最终一致性保障，即使 Redis 删除失败，下次缓存 miss 回填时也会排除已 ACK 的记录。

路径参数：`notification_uuid` — 公告 ID

**`DELETE /user-notifications/{notification_uuid}`**

删除（ACK）用户级公告。双写：在 PG 中设置 `deleted_at` 字段（软删除），在 Redis 中按 `notification_id` 匹配并删除该消息。

路径参数：`notification_uuid` — 公告 ID

**`DELETE /session-notifications/{session_uuid}/{notification_uuid}`**

删除（ACK）会话级公告。双写逻辑与用户级公告一致。按 `notification_id` 匹配并删除 Redis 消息。session_id 已关联唯一用户。

路径参数：
- `session_uuid` — 会话 ID
- `notification_uuid` — 公告 ID

## 文件结构

```
api/system_notification/              # 核心模块
├── __init__.py
├── sql_stat/                         # SQL 模板（参照 api/user_pod_scheduler/sql_stat/ 的模式）
│   ├── system_notification/
│   │   ├── SystemNotification.sql    # 建表、CRUD SQL 语句
│   │   ├── utils.py                  # 数据模型与异步数据库操作函数
│   │   └── __init__.py
│   ├── system_notification_ack/
│   │   ├── SystemNotificationAck.sql
│   │   ├── utils.py
│   │   └── __init__.py
│   ├── user_notification/
│   │   ├── UserNotification.sql
│   │   ├── utils.py
│   │   └── __init__.py
│   └── session_notification/
│       ├── SessionNotification.sql
│       ├── utils.py
│       └── __init__.py
├── redis_ops.py                      # Redis Stream 读写操作 + 系统级公告缓存清理
├── dual_write.py                     # Redis + PG 双写工具函数（用户级/会话级）
└── notification_service.py           # 公告服务层（供主应用和 Task Pod 直接调用）

api/system_notification_task/         # 系统级公告 Task Pod
├── __init__.py
└── task_app.py                       # Task Pod 入口（创建公告 + 清理缓存）

api/app/system_notification/          # FastAPI 应用模块
├── __init__.py
├── router_declare.py                 # 路由声明
├── data_model.py                     # Pydantic 请求/响应模型
└── endpoints.py                      # 接口实现

api/app/system_notification_app.py    # 应用启动入口
api/system_notification_app.sh        # 读取服务启动脚本
api/system_notification_task.sh       # Task Pod 启动脚本
k8s/base/12.2-system-notification-api.yaml    # 读取服务 K8s 部署配置
k8s/base/12.3-system-notification-task.yaml   # Task Pod K8s 部署配置
```

**关键文件说明**：

- `sql_stat/` 目录下的 SQL 文件遵循项目已有的 `-- LabelName` 注释分隔模式，由 `api/sql_utils/utils.py` 中的 `parse_sql_file` 解析。
- `redis_ops.py` 封装 Redis Stream 的读写操作和系统级公告的缓存清理逻辑，依赖项目中已有的 Redis 客户端（`api/redis/constants.py` 中的 `CLIENT`）。
- `dual_write.py` 提供用户级/会话级公告的双写函数，系统级公告不使用此模块。
- `notification_service.py` 作为对外暴露的服务层，提供用户级/会话级公告的写入函数（`create_user_notification`、`create_session_notification`，双写）和所有级别公告的读取/ACK 函数。
- `system_notification_task/` 为独立的 Task Pod 模块，负责系统级公告的创建和缓存清理。
- `system_notification_app.py` 的结构参照 `api/app/user_pod_scheduler_app.py`，使用 lifespan 管理初始化和关闭逻辑。
- `k8s/base/12.2-system-notification-api.yaml` 参照 `k8s/base/12.1-user-pod-scheduler.yaml` 的格式编写读取服务配置。
- `k8s/base/12.3-system-notification-task.yaml` 编写 Task Pod 的 Deployment 配置。
