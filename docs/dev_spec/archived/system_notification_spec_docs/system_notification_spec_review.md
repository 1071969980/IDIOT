---
文档标题：system_notification_spec_review
文档描述：系统公告功能开发完成后的审核目标和测试建议。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

# 系统公告功能审核与测试

**目录**:
- [审核目标](#审核目标)
  - [数据库审核](#数据库审核)
  - [Redis审核](#redis审核)
  - [双写一致性审核](#双写一致性审核)
  - [系统级公告缓存策略审核](#系统级公告缓存策略审核)
  - [API接口审核](#api接口审核)
  - [K8s部署审核](#k8s部署审核)
- [测试建议](#测试建议)
  - [单元测试](#单元测试)
  - [集成测试](#集成测试)
  - [端到端测试](#端到端测试)
- [性能考量](#性能考量)

---

相关文档：
- [开发上下文](./system_notification_spec_context.md) — 项目基础设施与编码模式
- [功能设计文档](./system_notification_spec_design.md) — 需求定义、数据模型与API设计

---

## 审核目标

### 数据库审核

对照设计文档中 [PostgreSQL 表设计](./system_notification_spec_design.md#postgresql-表设计) 的四张表逐一审核：

1. **表结构正确性**：
   - `system_notifications`、`system_notification_acks`、`user_notifications`、`session_notifications` 四张表是否全部创建
   - 每张表的字段名称、类型、约束是否与设计文档一致
   - 主键是否使用 `uuidv7()` 作为默认值（参见 [数据模型与UUID规则](./system_notification_spec_context.md#13-数据模型与uuid规则)）
   - `created_at` / `updated_at` 字段是否使用 `TIMESTAMPTZ` 类型且默认值为 `NOW()`

2. **索引有效性**：
   - `system_notification_acks` 表的联合唯一约束 `UNIQUE(notification_id, user_id)` 是否已创建，用于防止重复 ACK
   - `user_notifications` 表的 `user_id` 索引和 `deleted_at IS NULL` 部分索引是否已创建
   - `session_notifications` 表的 `(session_id)` 索引和 `deleted_at IS NULL` 部分索引是否已创建

3. **UUID生成**：
   - 确认数据库已安装 `uuidv7()` 扩展函数
   - INSERT 语句使用 `RETURNING id` 获取生成的主键，不在 Python 层面手动生成 UUID

4. **触发器与约束**：
   - 三张需要 `updated_at` 自动更新的表（`system_notifications`、`user_notifications`、`session_notifications`）是否配置了自动更新触发器
   - 外键约束（如 `system_notification_acks.notification_id` -> `system_notifications.id`）是否正确设置

### Redis审核

对照设计文档中 [Redis Stream 设计](./system_notification_spec_design.md#redis-stream-设计) 审核：

1. **Key 命名一致性**：
   - 系统级公告 Stream Key 是否为 `sys_notif:user:{user_uuid}` 格式
   - 用户级公告 Stream Key 是否为 `user_notif:user:{user_uuid}` 格式
   - 会话级公告 Stream Key 是否为 `session_notif:session:{session_uuid}` 格式
   - Key 命名与 `redis_ops.py` 中的实际使用是否完全一致

2. **Stream 操作正确性**：
   - 用户级/会话级公告写入是否使用 `XADD`（entry ID 由 Redis 自动生成，UUID 存储在消息体 `notification_id` 字段中）
   - 用户级/会话级公告删除后是否通过 `find_and_delete_notification` 按 `notification_id` 匹配并从 Stream 中移除
   - 系统级公告是否**不维护** `acked_users` 字段（仅缓存未 ACK 列表，ACK 即按 notification_id 删除）

3. **TTL 设置合理性**：
   - Stream Key 是否设置了过期时间（默认 7 天），防止缓存清理失败时的长期脏数据
   - 空结果标记 Key 是否设置了与 Stream 相同的 TTL
   - TTL 时长是否与公告的业务生命周期匹配
   - 是否遵循项目已有的 Redis Stream 模式（`xadd` + `expire`，参见 [Stream操作](./system_notification_spec_context.md#22-stream操作)）

4. **缓存穿透防护**：
   - `read_with_cache_fallback` 在 PG 返回空列表时是否设置空结果标记 Key
   - 读取前是否检查空结果标记 Key，避免重复穿透到 PG
   - 缓存清理（`invalidate_all_system_notification_caches`）是否同时清理标记 Key
   - 标记 Key 的 TTL 是否与 Stream Key 一致

### 双写一致性审核

对照设计文档中 [双存储协同机制](./system_notification_spec_design.md#双存储协同机制) 审核。**注意：双写仅适用于用户级和会话级公告，系统级公告使用 cache-aside 模式。**

1. **写入顺序（先 PG 后 Redis）**：
   - 用户级/会话级公告的双写操作是否严格遵循"先写入 PostgreSQL，获取 UUID，再写入 Redis"的顺序
   - 是否避免了先写 Redis 再写 PG 的时序问题
   - Redis 写入失败时是否有错误日志记录，且不回滚 PostgreSQL（由后续回填机制修复）

2. **读取回填逻辑**：
   - Redis 读取失败时（Key 不存在、连接异常等）是否正确回退到 PG 读取
   - PG 读取成功后是否将数据回填到 Redis Stream 并设置 TTL
   - 回填操作在读取响应路径中同步执行（会略微增加首次响应延迟，但保证返回前数据已写入缓存）

3. **ACK 后的 Redis 清理**：
   - 用户级/会话级公告删除后，Redis Stream 中对应消息是否通过 `find_and_delete_notification` 按 `notification_id` 移除
   - 清理操作失败时是否有重试或补偿机制

### 系统级公告缓存策略审核

对照设计文档中 [系统级公告生命周期](./system_notification_spec_design.md#三类公告的生命周期) 和 [缓存策略](./system_notification_spec_design.md#redis-stream-设计) 审核：

1. **创建流程（Task Pod）**：
   - Task Pod 是否只写入 PG `system_notifications` 表，不进行 Redis 双写
   - 创建后是否调用 `invalidate_all_system_notification_caches()` 清理所有用户的系统级公告缓存
   - 缓存清理失败时是否只记日志，不回滚 PG 写入（依赖 TTL 兜底）

2. **读取流程（cache-aside）**：
   - 用户读取时先检查 Redis 缓存 `sys_notif:user:{user_uuid}`
   - 缓存 miss 时从 PG 查询未 ACK 的系统级公告（`NOT EXISTS` 子查询排除已确认记录）
   - 回填 Redis 时是否设置了 TTL

3. **ACK 流程**：
   - ACK 时先在 PG `system_notification_acks` 表插入确认记录
   - PG ACK 成功后从 Redis 缓存中按 `notification_id` 查找并删除该消息（`find_and_delete_notification`）
   - 即使 Redis 删除失败，PG 已 ACK，下次缓存 miss 回填时自动排除

### API接口审核

对照设计文档中 [API 设计](./system_notification_spec_design.md#api-设计) 审核：

1. **认证正确性**：
   - 读取接口（`GET /system-notifications`、`GET /user-notifications`）是否正确使用认证依赖（参见 [认证依赖](./system_notification_spec_context.md#33-认证依赖)）
   - 会话级公告接口是否校验了用户对该会话的访问权限（注意：session_id 已关联唯一用户，接口需传入 session_id 和 user_id，服务层校验归属关系）

2. **请求/响应模型一致性**：
   - Pydantic 模型定义是否与设计文档中的请求体/响应体格式一致
   - `data_model.py` 中的字段名称和类型是否与 API 文档描述匹配
   - 响应体中是否包含所有必要字段（`id`、`level`、`content`、`created_at`）

3. **错误处理**：
   - 无效的 UUID 参数是否返回 422 错误
   - 不存在的公告 ACK/删除是否返回 404 错误
   - 重复 ACK 是否被正确处理（幂等性——返回 `already_acked` 而非报错）
   - Redis 连接异常时是否优雅降级到 PG 读取

### K8s部署审核

对照设计文档中 [文件结构](./system_notification_spec_design.md#文件结构) 和 [K8s部署模式](./system_notification_spec_context.md#4-k8s部署模式) 审核：

1. **读取服务部署**：
   - `12.2-system-notification-api.yaml` 中的 Deployment 和 Service 配置是否正确
   - ConfigMap/Secret 引用是否正确（`idiot-config`、`idiot-secrets`）
   - 资源限制是否合理（requests 256Mi/100m，limits 1Gi/500m）
   - 健康检查是否配置

2. **Task Pod 部署**：
   - `12.3-system-notification-task.yaml` 中的 Deployment 配置是否正确
   - Task Pod 使用 `./api/system_notification_task.sh` 启动
   - Task Pod 的资源限制是否合理（无需持续运行，可设置较低资源）

3. **Kustomization**：
   - `k8s/base/kustomization.yaml` 中是否已添加 `12.2` 和 `12.3` 两个资源文件引用
   - 资源文件编号是否按序排列

---

## 测试建议

### 单元测试

1. **SQL 工具函数测试**：
   - 测试四张表的 CRUD 操作函数是否正确
   - 验证 `parse_sql_file()` 对公告模块 SQL 文件的解析结果是否包含所有预期的 SQL 语句键名
   - 验证 INSERT 操作是否正确返回 UUID（`RETURNING id`）
   - 验证软删除操作是否正确设置 `deleted_at` 字段
   - 验证批量查询是否正确过滤 `deleted_at IS NULL` 的记录

2. **Redis 操作函数测试**：
   - 测试 `redis_ops.py` 中 Stream 写入函数是否使用正确的 Key 格式，且 entry ID 由 Redis 自动生成
   - 测试 `find_and_delete_notification()` 能否按 `notification_id` 正确定位并删除消息
   - 测试 `invalidate_all_system_notification_caches()` 是否能正确清理所有匹配的 Key（含标记 Key）
   - 测试空结果标记 Key 的设置和检查功能
   - 测试用户级/会话级公告的 Stream 消息移除操作
   - 模拟 Redis 连接异常，验证错误处理逻辑

3. **双写逻辑测试**：
   - 测试 `dual_write.py` 中双写函数的执行顺序（先 PG 后 Redis）
   - 模拟 Redis 写入失败场景，验证是否记录错误日志且不回滚 PG
   - 验证回填逻辑：Redis miss -> PG 读取 -> Redis 写入 + TTL

4. **服务层函数测试**：
   - 测试 `notification_service.py` 中用户级/会话级公告创建的完整逻辑
   - 测试系统级公告的 ACK 操作（先 DB 后 Redis 删除）
   - 测试 ACK 操作的幂等性（重复 ACK 不应报错）

5. **Task Pod 函数测试**：
   - 测试 `task_app.py` 中 `create_system_notification` 的完整流程
   - 模拟缓存清理失败，验证 PG 写入不受影响
   - 验证返回的 UUID 与 PG 中记录一致

### 集成测试

1. **用户级/会话级公告的双写流程测试**：
   - 创建公告 -> 验证 PG 和 Redis 中都存在对应记录
   - 删除公告 -> 验证 PG 软删除和 Redis 清理

2. **系统级公告的 cache-aside 流程测试**：
   - Task Pod 创建系统公告 -> 验证仅 PG 中有记录，Redis 缓存已被清理
   - 用户读取 -> 验证从 PG 回填到 Redis（cache miss -> PG -> 回填）
   - 用户再次读取 -> 验证直接从 Redis 返回（cache hit）
   - 用户 ACK -> 验证 PG 插入确认记录 + Redis 删除消息
   - 其他未 ACK 用户读取 -> 验证仍能看到该公告

3. **Redis 宕机时的降级读取**：
   - 模拟 Redis 不可用 -> 发起读取请求 -> 验证从 PG 正确读取
   - 验证 PG 读取后是否将数据回填到 Redis
   - Redis 恢复后验证后续读取是否直接从 Redis 返回

4. **并发 ACK 的幂等性**：
   - 多个请求同时对同一系统级公告进行 ACK
   - 验证 `system_notification_acks` 表的联合唯一索引生效，无重复记录
   - 验证幂等性（第二次 ACK 不报错）

5. **缓存清理的完整性**：
   - 创建多个用户的系统级公告缓存 -> 创建新公告 -> 验证所有用户缓存被清理
   - 验证清理后各用户首次读取均从 PG 回填

### 端到端测试

1. **系统级公告的完整生命周期**：
   - Task Pod 创建系统公告（只写 DB + 清缓存）
   - 用户通过 `GET /system-notifications` 获取未 ACK 的公告列表（cache miss -> PG 回填）
   - 用户通过 `POST /system-notifications/{uuid}/ack` 确认公告（先 DB ACK 后删缓存）
   - 用户再次获取公告列表，验证已确认的公告不再出现
   - 其他未确认用户仍然可以看到该公告

2. **用户级公告的完整生命周期**：
   - 通过 Python 函数调用 `notification_service.create_user_notification()` 为指定用户创建公告（双写）
   - 目标用户通过 `GET /user-notifications` 获取公告列表
   - 目标用户通过 `DELETE /user-notifications/{uuid}` 删除公告
   - 验证删除后该公告不再出现
   - 验证非目标用户无法看到该公告

3. **会话级公告的完整生命周期**：
   - 通过 Python 函数调用 `notification_service.create_session_notification()` 为指定会话创建公告（双写）
   - 会话用户通过 `GET /session-notifications/{session_uuid}` 获取公告列表
   - 会话用户通过 `DELETE /session-notifications/{session_uuid}/{notification_uuid}` 删除公告
   - 验证删除后该公告不再出现
   - 验证其他会话的公告列表不受影响

---

## 性能考量

### 系统级公告缓存清理效率

系统级公告创建后需要清理所有用户的 Redis 缓存（`sys_notif:user:*`），使用 `SCAN + UNLINK` 模式。

**关注点**：
- `SCAN` 迭代的性能是否可接受（系统级公告创建频率极低，通常为运维操作）
- `UNLINK`（异步删除）是否被正确使用，避免阻塞 Redis
- 缓存清理失败时的 TTL 兜底是否可靠（默认 7 天）

### Redis Stream 的内存使用

每条公告在 Redis Stream 中以消息形式存储。系统级公告仅在用户首次读取时回填，不预先写入。

**关注点**：
- 系统级公告采用按需回填，只为活跃用户创建缓存，内存使用更可控
- TTL 设置是否有效防止过期数据堆积
- 是否需要设置 Stream 的 MAXLEN 限制，防止单个 Stream 无限增长
- 建议监控 Redis 的 `used_memory` 和 Stream 的长度指标

### 大量未 ACK 公告的查询性能

系统级公告需要过滤已 ACK 的记录，当未 ACK 公告数量较多时查询可能变慢。

**关注点**：
- PG 查询中使用 `NOT EXISTS` 子查询排除已确认记录的执行计划是否高效
- `system_notification_acks` 表的 `(user_id, notification_id)` 联合唯一约束是否被查询优化器正确使用
- 建议在测试环境中模拟大量公告数据（如数千条公告、数百用户），验证查询响应时间
