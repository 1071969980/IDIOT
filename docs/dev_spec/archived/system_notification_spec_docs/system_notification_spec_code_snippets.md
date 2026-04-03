---
文档标题：system_notification_spec_code_snippets
文档描述：系统公告功能的关键代码样板，包含SQL模板、Redis操作、双写机制、FastAPI接口等实现参考。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

# 系统公告功能代码片段

## 目录

- [1. SQL模板文件](#1-sql模板文件)
- [2. Python数据模型与数据库操作](#2-python数据模型与数据库操作)
- [3. Redis操作与双写工具](#3-redis操作与双写工具)
- [4. 通知服务层、Task Pod与FastAPI接口](#4-通知服务层task-pod与fastapi接口)
- [5. 应用部署配置](#5-应用部署配置)

---

本文档为系统公告功能的代码片段索引，详细代码按章节拆分为独立文件，位于同名文件夹 `system_notification_spec_code_snippets/` 下。

代码片段严格遵循项目已有模式，相关上下文参见：
- [system_notification_spec_context.md](./system_notification_spec_context.md) -- 项目基础设施与开发上下文
- [system_notification_spec_design.md](./system_notification_spec_design.md) -- 功能设计文档

## 1. SQL模板文件

详细代码：[sql_templates.md](./system_notification_spec_code_snippets/sql_templates.md)

包含四张表的SQL模板定义：

| SQL文件 | 对应表 | 关键特性 |
|---------|--------|----------|
| `SystemNotification.sql` | `system_notifications` | `updated_at` 自动更新触发器，`created_at DESC` 索引 |
| `SystemNotificationAck.sql` | `system_notification_acks` | `(notification_id, user_id)` 联合唯一约束，`ON CONFLICT DO NOTHING` |
| `UserNotification.sql` | `user_notifications` | `deleted_at IS NULL` 部分索引实现软删除过滤 |
| `SessionNotification.sql` | `session_notifications` | `(session_id)` 索引 + `deleted_at IS NULL` 部分索引 + 软删除 |

所有SQL文件遵循 `-- LabelName` 注释分隔规范，由 `api/sql_utils/utils.py` 中的 `parse_sql_file` 解析。

文件位置模式：`api/system_notification/sql_stat/[table_name]/[TableName].sql`

## 2. Python数据模型与数据库操作

详细代码：[data_models_and_db_ops.md](./system_notification_spec_code_snippets/data_models_and_db_ops.md)

数据模型命名规范（`@dataclass`，下划线前缀）：

| 数据模型 | 用途 | 所在文件 |
|----------|------|----------|
| `_SystemNotificationCreate` | 创建系统公告入参 | `sql_stat/system_notification/utils.py` |
| `_SystemNotificationResult` | 系统公告查询结果 | 同上 |
| `_SystemNotificationAckCreate` | 系统公告确认入参 | `sql_stat/system_notification_ack/utils.py` |
| `_UserNotificationCreate` | 创建用户公告入参 | `sql_stat/user_notification/utils.py` |
| `_UserNotificationResult` | 用户公告结果（含 `deleted_at`） | 同上 |
| `_SessionNotificationCreate` | 创建会话公告入参 | `sql_stat/session_notification/utils.py` |

数据库操作模式参照 `api/user_pod_scheduler/sql_stat/utils.py`：
- 连接：`ASYNC_SQL_ENGINE.connect()`
- UUID：由数据库 `uuidv7()` 生成，Python 通过 `RETURNING id` 获取
- 建表：`CREATE_TABLE` 为 `list[str]`，循环执行

## 3. Redis操作与双写工具

详细代码：[redis_and_dual_write.md](./system_notification_spec_code_snippets/redis_and_dual_write.md)

### Redis操作（redis_ops.py）

依赖项目已有的 Redis 客户端（`api/redis/constants.py` 中的 `CLIENT`）。

Redis Stream Key 命名规范：

| Key 模式 | 用途 | 对应公告级别 |
|----------|------|--------------|
| `sys_notif:user:{user_uuid}` | 系统级公告缓存（仅存未 ACK） | 全体用户 |
| `user_notif:user:{user_uuid}` | 用户级公告 | 指定用户 |
| `session_notif:session:{session_uuid}` | 会话级公告 | 指定会话 |

默认TTL：`86400 * 7`（7天），作为缓存清理失败时的兜底机制。

核心函数：

| 函数 | 用途 |
|------|------|
| `write_notification_to_redis()` | 写入一条公告到 Stream 并设置 TTL（entry ID 由 Redis 自动生成，UUID 存于消息体） |
| `read_notifications_from_redis()` | 从 Stream 读取所有公告（从消息体中提取 notification_id 作为公告 ID） |
| `find_and_delete_notification()` | 遍历 Stream 匹配 notification_id 后删除（XRANGE + XDEL） |
| `delete_notification_from_redis()` | 删除指定公告（封装 `find_and_delete_notification`） |
| `set_empty_marker()` | 设置空结果标记 Key，防止缓存穿透 |
| `check_empty_marker()` | 检查空结果标记 Key 是否存在 |
| `invalidate_all_system_notification_caches()` | 清理所有用户的系统级公告缓存及标记 Key（SCAN + UNLINK） |

### 双写工具（dual_write.py）

**仅用于用户级和会话级公告**。系统级公告采用"只写 DB + 清缓存"策略。

| 函数 | 用途 | 写入顺序 |
|------|------|----------|
| `write_notification_with_dual_write()` | 创建用户级/会话级公告 | PG -> Redis |
| `ack_with_dual_write()` | 确认/删除公告 | PG ACK -> Redis删除（按 notification_id 匹配） |
| `read_with_cache_fallback()` | 读取公告（含空结果标记防护） | 检查标记 -> Redis -> PG回填 |

设计原则：PG写入失败则整体失败；Redis写入失败仅记录日志不回滚，由回填机制修复。

## 4. 通知服务层、Task Pod与FastAPI接口

详细代码：[service_and_endpoints.md](./system_notification_spec_code_snippets/service_and_endpoints.md)

### 通知服务层（notification_service.py）

文件位置：`api/system_notification/notification_service.py`

主应用通过 Python 函数直接调用，无需经过 HTTP。提供以下方法：

**系统级公告（读取 + ACK，无创建函数）**：
- `get_unacked_system_notifications(user_id)` -- cache-aside 获取未确认系统公告（含空结果标记防护）
- `ack_system_notification(notification_id, user_id)` -- 先 DB ACK 后删缓存（按 notification_id 匹配）。幂等：重复 ACK 返回 None 而非报错

**用户级公告（读取 + 删除）**：
- `get_user_notifications(user_id)` -- 获取用户级公告
- `delete_user_notification(notification_id, user_id)` -- 双写删除（按 notification_id 匹配 Redis 消息）

**会话级公告（读取 + 删除）**：
- `get_session_notifications(session_id)` -- 获取会话级公告（session_id 已关联唯一用户）
- `delete_session_notification(notification_id, session_id)` -- 双写删除（session_id 已关联唯一用户）

### Task Pod（task_app.py）

文件位置：`api/system_notification_task/task_app.py`

作为一次性 Job 运行，通过 CLI 参数（`--level`、`--content`）传入公告信息。启动脚本：`api/system_notification_task.sh`。

- `create_system_notification(level, content)` -- 写入 PG + 清理所有用户缓存

### FastAPI接口（endpoints.py）

路由前缀：`/system-notification`，标签：`system-notification`。目前不提供 HTTP 管理写入接口。

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/system-notifications` | 获取未ACK系统公告 |
| POST | `/system-notifications/{id}/ack` | 确认系统公告（幂等：已 ACK 返回 `already_acked`） |
| GET | `/user-notifications` | 获取用户级公告 |
| DELETE | `/user-notifications/{id}` | 删除用户级公告 |
| GET | `/session-notifications/{session_id}` | 获取会话级公告 |
| DELETE | `/session-notifications/{session_id}/{id}` | 删除会话级公告 |

认证依赖：`Annotated[_User, Depends(get_current_active_user)]`

## 5. 应用部署配置

详细代码：[deployment.md](./system_notification_spec_code_snippets/deployment.md)

### 读取服务

- 应用入口：`api/app/system_notification_app.py`，参照 `api/app/main.py`
- 独立 FastAPI 应用，端口 8001
- `root_path="/system-notification"`
- `init_db` 使用 `@distributed_lock("init_notification_db")` 保护，防止多实例并发初始化
- 启动脚本：`api/system_notification_app.sh`（生产模式不加 `--preload`）

### Task Pod

- 入口：`api/system_notification_task/task_app.py`
- 一次性 Job，通过 CLI 参数 `--level`、`--content` 传入公告信息
- 启动脚本：`api/system_notification_task.sh`

### K8s部署

- 读取服务：`k8s/base/12.2-system-notification-api.yaml`（Deployment + Service）
- Task Pod：`k8s/base/12.3-system-notification-task.yaml`（CronJob，`suspend: true`，手动触发）
- 需在 `k8s/base/kustomization.yaml` 中添加引用
