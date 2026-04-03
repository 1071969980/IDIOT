---
文档标题：system_notification_spec_todo
文档描述：系统公告功能实际开发阶段的待办事项列表。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

# 系统公告功能开发待办事项

**目录**:
- [阶段一：基础设施](#阶段一基础设施)
- [阶段二：核心模块开发](#阶段二核心模块开发)
- [阶段三：FastAPI应用与Task Pod](#阶段三fastapi应用与task-pod)
- [阶段四：部署配置](#阶段四部署配置)
- [阶段五：测试与验证](#阶段五测试与验证)

---

相关文档：
- [开发上下文](./system_notification_spec_context.md) — 项目基础设施与编码模式
- [功能设计文档](./system_notification_spec_design.md) — 需求定义、数据模型与API设计
- [审核与测试](./system_notification_spec_review.md) — 审核目标与测试建议

---

## 阶段一：基础设施

本阶段搭建公告模块的目录结构、SQL模板和数据模型。参照项目已有的 SQL 模板系统（[SQL模板系统](./system_notification_spec_context.md#11-sql模板系统)）和数据模型规范（[数据模型与UUID规则](./system_notification_spec_context.md#13-数据模型与uuid规则)）。

- [ ] **创建模块目录结构** `api/system_notification/`
  创建主模块目录及 `__init__.py`，后续所有核心文件均位于此目录下。参见设计文档 [文件结构](./system_notification_spec_design.md#文件结构)。

- [ ] **创建 SQL 模板目录和文件** — `system_notifications` 表
  在 `api/system_notification/sql_stat/system_notification/` 下创建 `SystemNotification.sql` 和 `utils.py`。SQL 文件使用 `-- LabelName` 注释分隔模式，包含建表语句和 CRUD 操作（含 `get_unacked`：`NOT EXISTS` 子查询排除已确认记录）。参见 [PostgreSQL 表设计 - system_notifications](./system_notification_spec_design.md#postgresql-表设计)。

- [ ] **创建 SQL 模板目录和文件** — `system_notification_acks` 表
  在 `api/system_notification/sql_stat/system_notification_ack/` 下创建 `SystemNotificationAck.sql` 和 `utils.py`。包含建表语句、插入 ACK 记录（`ON CONFLICT DO NOTHING` 保证幂等）、按用户查询已 ACK 公告列表等操作。

- [ ] **创建 SQL 模板目录和文件** — `user_notifications` 表
  在 `api/system_notification/sql_stat/user_notification/` 下创建 `UserNotification.sql` 和 `utils.py`。包含建表语句、插入、查询（含 `deleted_at IS NULL` 过滤）、软删除操作。

- [ ] **创建 SQL 模板目录和文件** — `session_notifications` 表
  在 `api/system_notification/sql_stat/session_notification/` 下创建 `SessionNotification.sql` 和 `utils.py`。包含建表语句、插入、按会话查询（`session_id` 已关联唯一用户，查询和软删除只需 `session_id`）、软删除操作。

- [ ] **创建 `@dataclass` 数据模型**
  在各 `utils.py` 中定义创建用的数据模型（如 `_SystemNotificationCreate`、`_UserNotificationCreate`、`_SessionNotificationCreate`），命名以下划线开头。模型不包含 UUID 字段（由数据库生成）。参见 [数据模型与UUID规则](./system_notification_spec_context.md#13-数据模型与uuid规则)。

- [ ] **创建 SQL 工具函数（CRUD 操作）**
  在各 `utils.py` 中实现异步数据库操作函数：插入并 `RETURNING id`、按条件查询、软删除更新等。使用 `ASYNC_SQL_ENGINE` 和 `parse_sql_file()` 的标准模式。

## 阶段二：核心模块开发

本阶段实现 Redis 操作、双写机制和服务层。参照设计文档中 [双存储协同机制](./system_notification_spec_design.md#双存储协同机制)。

- [ ] **实现 Redis 操作工具** `redis_ops.py`
  创建 `api/system_notification/redis_ops.py`，封装 Redis Stream 的读写操作：按 Key 写入公告消息（带 TTL，entry ID 由 Redis 自动生成，UUID 存于消息体）、按 Key 读取公告列表（从消息体提取 notification_id）、按 `notification_id` 查找并删除指定消息。实现空结果标记 Key 机制（`set_empty_marker`、`check_empty_marker`）防止缓存穿透。实现 `invalidate_all_system_notification_caches()` 函数，使用 `SCAN MATCH sys_notif:user:*` + `UNLINK` 清理所有用户的系统级公告缓存和标记 Key。使用项目已有的 Redis 客户端 `CLIENT`（参见 [连接配置](./system_notification_spec_context.md#21-连接配置)）。

- [ ] **实现双写机制** `dual_write.py`
  创建 `api/system_notification/dual_write.py`，提供用户级/会话级公告的双写函数。写入顺序：先 PG 获取 UUID，再 Redis 写入（使用返回的 `result.id` 作为 `notification_id`）。Redis 失败时记录日志但不回滚 PG。**注意**：系统级公告不使用此模块。参见 [双写一致性审核](./system_notification_spec_review.md#双写一致性审核)。

- [ ] **实现回填逻辑**
  在 `dual_write.py` 中实现 `read_with_cache_fallback`：Redis 读取失败时，从 PG 读取数据并写入 Redis Stream，设置 TTL。参见 [读取流程（Redis 优先 + 回填）](./system_notification_spec_design.md#双存储协同机制)。

- [ ] **实现通知服务层** `notification_service.py`
  创建 `api/system_notification/notification_service.py`，作为对外暴露的服务层。**系统级公告**：仅提供 `get_unacked_system_notifications`（cache-aside 读取，含空结果标记防护）和 `ack_system_notification`（先 DB 后删缓存，返回 `bool | None`），不提供创建函数。**用户级/会话级公告**：提供创建（`create_user_notification`、`create_session_notification`，双写）、读取、删除函数。会话级读取和删除函数接受可选的 `user_id` 参数用于权限校验（session_id 已关联唯一 user_id）。参见 [通知服务层](./system_notification_spec_code_snippets.md#4-通知服务层与fastapi接口)。

- [ ] **实现系统级公告 Task Pod** `api/system_notification_task/`
  创建 `api/system_notification_task/task_app.py`，实现 `create_system_notification(level, content)` 函数：写入 PG -> 调用 `invalidate_all_system_notification_caches()` 清理缓存。包含 CLI 入口（`argparse`）和 `if __name__ == "__main__"` 启动代码，作为一次性 Job 运行。参见 [Task Pod 入口](./system_notification_spec_code_snippets.md#task-pod-入口task_apppy)。

- [ ] **创建 Task Pod 启动脚本**
  创建 `api/system_notification_task.sh`，激活虚拟环境后调用 `python -m api.system_notification_task.task_app "$@"`，透传 CLI 参数。参见 [Task Pod 启动脚本](./system_notification_spec_code_snippets.md#task-pod-启动脚本)。

## 阶段三：FastAPI应用与Task Pod

本阶段创建独立的 FastAPI 读取服务应用进程和 Task Pod。参照项目已有的独立应用模式（[独立FastAPI应用的创建](./system_notification_spec_context.md#5-独立fastapi应用的创建)）。

- [ ] **创建 Pydantic 请求/响应模型**
  创建 `api/app/system_notification/data_model.py`，定义所有接口的请求体和响应体 Pydantic 模型。参见设计文档 [API 设计](./system_notification_spec_design.md#api-设计) 中的请求体和响应体格式。

- [ ] **创建路由声明**
  创建 `api/app/system_notification/router_declare.py`，定义 `APIRouter` 实例，配置 `prefix` 和 `tags`。参见 [模块化路由组织](./system_notification_spec_context.md#32-模块化路由组织)。

- [ ] **实现接口端点**
  创建 `api/app/system_notification/endpoints.py`，实现所有 API 端点：读取接口（3个）、ACK 与删除接口（3个）。接口逻辑调用服务层函数。用户级/会话级公告的创建通过 Python 函数直接调用 `notification_service.py`，目前不提供 HTTP 管理端点。参见 [API 设计](./system_notification_spec_design.md#api-设计)。

- [ ] **创建读取服务应用启动入口**
  创建 `api/app/system_notification_app.py`，使用 `asynccontextmanager` 管理 `lifespan`，在启动阶段使用 `@distributed_lock("init_notification_db")` 保护数据库表初始化（这是对主应用 `@distributed_lock("init_postgres_db")` 模式的借鉴与改进，User Pod Scheduler 应用未使用此模式）。配置独立的 `root_path`（如 `/system-notification`）。参见 [应用入口文件](./system_notification_spec_context.md#51-应用入口文件)。

- [ ] **创建读取服务启动脚本**
  创建 `api/system_notification_app.sh`，参考 `api/run_user_pod_scheduler.sh` 模式，使用独立的端口号（如 8001）。调试模式用 uvicorn，生产模式用 gunicorn（不加 `--preload`）。参见 [独立启动脚本](./system_notification_spec_context.md#52-独立启动脚本)。

## 阶段四：部署配置

本阶段配置 K8s 部署。参照项目已有的 K8s 部署模式（[K8s部署模式](./system_notification_spec_context.md#4-k8s部署模式)）。

- [ ] **创建读取服务 K8s Deployment/Service YAML**
  创建 `k8s/base/12.2-system-notification-api.yaml`（编号接在 `12.1-user-pod-scheduler.yaml` 之后），包含 Deployment 和 Service 配置。使用相同的 `idiot-api:latest` 镜像，启动命令改为 `./api/system_notification_app.sh`。参见 [独立K8s部署配置](./system_notification_spec_context.md#53-独立k8s部署配置)。

- [ ] **创建 Task Pod K8s CronJob YAML**
  创建 `k8s/base/12.3-system-notification-task.yaml`，包含 CronJob 配置。使用 `suspend: true` + 不可能的 schedule 禁止自动调度，通过 `kubectl create job --from` 手动触发一次性执行。使用相同的 `idiot-api:latest` 镜像，启动命令为 `./api/system_notification_task.sh`，参数通过 `args` 传入。Task Pod 无需 Service（不对外暴露端口）。参见 [Task Pod K8s配置](./system_notification_spec_code_snippets.md#5-应用部署配置)。

- [ ] **更新 Kustomization 配置**
  在 `k8s/base/kustomization.yaml` 中添加 `12.2-system-notification-api.yaml` 和 `12.3-system-notification-task.yaml` 的资源引用。参见 [Kustomize管理](./system_notification_spec_context.md#41-kustomize管理)。

- [ ] **配置 ConfigMap 和 Secret 引用**
  在两个 Deployment 中通过 `configMapRef`（`idiot-config`）和 `secretRef`（`idiot-secrets`）注入环境变量，与主应用保持一致。参见 [ConfigMap与Secret](./system_notification_spec_context.md#44-configmap与secret)。

- [ ] **配置资源限制和健康检查**
  读取服务配置合理的 requests/limits（建议 requests 256Mi/100m，limits 1Gi/500m）。配置 `livenessProbe` 和 `readinessProbe`。Task Pod 配置较低的资源限制。参见 [K8s部署审核](./system_notification_spec_review.md#k8s部署审核)。

- [ ] **配置 Nginx 反向代理路由**
  在 Nginx 配置中添加公告读取服务的反向代理路由，将 `/system-notification` 路径的请求转发到公告服务的端口。

## 阶段五：测试与验证

本阶段按审核文档的建议进行测试。参见 [测试建议](./system_notification_spec_review.md#测试建议)。

- [ ] **验证数据库表创建和索引**
  连接 PostgreSQL，检查四张表是否正确创建，字段类型和约束是否符合设计。验证索引是否生效（联合唯一索引、部分索引）。验证 `updated_at` 触发器是否工作。

- [ ] **验证系统级公告的 cache-aside 流程**
  通过 Task Pod 创建系统公告 -> 验证仅 PG 有记录，Redis 缓存已清理 -> 用户读取 -> 验证从 PG 回填到 Redis -> 用户 ACK -> 验证 PG 插入确认记录 + Redis 删除消息。参见 [系统级公告缓存策略审核](./system_notification_spec_review.md#系统级公告缓存策略审核)。

- [ ] **验证用户级/会话级公告的双写和回填**
  通过服务层创建公告，验证 PG 和 Redis 中都有对应记录。手动删除 Redis Key 后发起读取，验证回填逻辑将数据重新写入 Redis。参见 [双写一致性审核](./system_notification_spec_review.md#双写一致性审核)。

- [ ] **验证 API 接口功能**
  使用 curl 或 HTTP 客户端测试所有接口端点：读取公告、ACK 系统公告、删除用户级/会话级公告。验证认证、参数校验、错误处理是否正确。参见 [API接口审核](./system_notification_spec_review.md#api接口审核)。

- [ ] **验证 K8s 部署**
  应用 K8s 配置后，检查读取服务 Pod 和 Task Pod 是否正常启动和运行。验证 Service 是否正确暴露端口。验证环境变量是否正确注入。验证健康检查是否通过。参见 [K8s部署审核](./system_notification_spec_review.md#k8s部署审核)。

- [ ] **验证端到端生命周期**
  分别测试系统级、用户级、会话级公告的完整生命周期：创建 -> 读取 -> ACK/删除 -> 验证不再出现。参见 [端到端测试](./system_notification_spec_review.md#端到端测试)。

- [ ] **验证并发 ACK 的幂等性**
  并发发起对同一系统级公告的 ACK 请求，验证不会产生重复记录。参见 [集成测试](./system_notification_spec_review.md#集成测试)。

- [ ] **验证缓存清理的完整性**
  创建多个用户的系统级公告缓存 -> 创建新系统公告 -> 验证所有用户缓存被清理 -> 各用户首次读取均从 PG 回填。
