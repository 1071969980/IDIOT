# 数据库设计文档

本文档从数据库设计角度描述 `api/chat/sql_stat/` 目录下的数据表结构和设计理念。

## 表架构概览

| 表名 | 用途 |
|------|------|
| `u2a_user_messages` | 用户消息记录（业务层） |
| `u2a_agent_messages` | Agent 消息记录（业务层） |
| `u2a_user_short_term_memory` | 用户短期记忆（LLM 上下文层） |
| `u2a_agent_short_term_memory` | Agent 短期记忆（LLM 上下文层） |
| `u2a_sessions` | 会话元数据 |
| `u2a_session_tasks` | 会话任务记录 |

---

## 序列索引设计

### 1. `seq_index` (序列索引)

**作用范围**: 会话级别 (`session_id`)

**应用表**: `u2a_user_messages`, `u2a_user_short_term_memory`

**递增规则**:
```sql
SELECT COALESCE(MAX(seq_index), -1) + 1
WHERE session_id = :session_id
```

**设计目的**:
- 为会话内的用户消息提供全局唯一的顺序标识
- 支持按时间顺序的查询和分页
- 用于跨任务的时序排序

---

### 2. `sub_seq_index` (子序列索引)

**作用范围**: 会话任务级别 (`session_id` + `session_task_id`)

**应用表**: `u2a_agent_messages`, `u2a_agent_short_term_memory`

**递增规则**:
```sql
SELECT COALESCE(MAX(sub_seq_index), -1) + 1
WHERE session_id = :session_id AND session_task_id = :session_task_id
```

**设计目的**:
- 为单个任务内的多条 Agent 消息提供局部顺序
- 允许 Agent 在一次任务中产生多条消息（思考、工具调用、最终回复等）
- 每个新任务从 0 重新开始计数

---

### 3. 两层序列架构

```
会话 (Session)
│
├─ Task A (用户 seq_index: 0-5)
│   ├─ 用户消息 (seq_index: 0)
│   ├─ Agent 消息 1 (sub_seq_index: 0)
│   ├─ Agent 消息 2 (sub_seq_index: 1)
│   ├─ 用户消息 (seq_index: 1)
│   └─ Agent 消息 3 (sub_seq_index: 2)
│
└─ Task B (用户 seq_index: 6-10)
    ├─ 用户消息 (seq_index: 6)
    ├─ Agent 消息 1 (sub_seq_index: 0)  ← 新任务重新计数
    └─ Agent 消息 2 (sub_seq_index: 1)
```

**设计优势**:
- 用户消息具有全局时序，便于跨任务查询
- Agent 消息按任务局部排序，反映任务内部的逻辑流

---

## Message 表 vs Memory 表

### 设计理念分离

| 维度 | Message 表 | Memory 表 |
|------|-----------|-----------|
| **关注点** | 业务流程管理 | LLM 上下文构建 |
| **内容格式** | `TEXT` | `JSONB` |
| **状态字段** | 有 | 无 |
| **可压缩性** | 不可删除 | 可被压缩清理 |
| **主要用途** | 消息状态追踪、历史展示 | 传递给 LLM 的对话历史 |

---

### Message 表 (`u2a_user_messages` / `u2a_agent_messages`)

**核心字段**:
- `message_type`: 消息类型（text/tool_call/等）
- `content` (TEXT): 原始消息内容
- `status`: 处理状态
- `seq_index` / `sub_seq_index`: 顺序索引
- `updated_at`: 更新时间戳

**用户消息状态枚举**:
- `agent_working_for_user`: Agent 正在处理
- `waiting_agent_ack_user`: 等待 Agent 确认
- `completed`: 已完成
- `error`: 错误

**Agent 消息状态枚举**:
- `streaming`: 流式生成中
- `stop`: 已停止
- `completed`: 已完成
- `error`: 错误

**设计特点**:
- 有状态管理，支持消息生命周期追踪
- 支持分页查询（按 `seq_index` 倒序）
- 通过触发器自动维护时间戳
- Agent 消息支持 `json_content` 字段存储额外结构化数据

---

### Memory 表 (`u2a_user_short_term_memory` / `u2a_agent_short_term_memory`)

**核心字段**:
- `content` (JSONB): 结构化的对话消息（兼容 OpenAI API 格式）
- `seq_index` / `sub_seq_index`: 顺序索引
- `session_task_id`: 关联的任务 ID

**设计特点**:
- 无状态字段，纯粹的数据存储
- JSONB 格式直接兼容 LLM API
- 可被压缩以优化 token 使用
- 按 `session_task_id` 分组后按索引排序

---

## 表关系图

```
u2a_sessions (会话)
    │
    ├─ u2a_session_tasks (任务)
    │       │
    │       ├─ u2a_user_messages (用户消息)
    │       │       └─ seq_index: 全局递增
    │       │
    │       ├─ u2a_agent_messages (Agent消息)
    │       │       └─ sub_seq_index: 任务内递增
    │       │
    │       ├─ u2a_user_short_term_memory (用户记忆)
    │       │       └─ seq_index: 全局递增
    │       │
    │       └─ u2a_agent_short_term_memory (Agent记忆)
    │               └─ sub_seq_index: 任务内递增
```

---

## 索引设计

### 索引策略

所有表均创建以下索引以优化查询性能：

```sql
-- 会话查询
CREATE INDEX idx_*_session_id ON table_name (session_id);

-- 用户查询
CREATE INDEX idx_*_user_id ON table_name (user_id);

-- 任务查询
CREATE INDEX idx_*_session_task_id ON table_name (session_task_id);

-- 状态查询（仅 Message 表）
CREATE INDEX idx_*_status ON table_name (status);
```

### 查询模式优化

- **按会话查询**: 使用 `session_id` 索引，按序列索引排序
- **按任务查询**: 使用 `session_task_id` 索引，按子序列索引排序
- **分页查询**: 利用序列索引的范围查询

---

## 外键约束

```sql
-- 用户/Agent 关联
FOREIGN KEY (user_id) REFERENCES simple_users(id) ON DELETE CASCADE

-- 会话关联
FOREIGN KEY (session_id) REFERENCES u2a_sessions(id) ON DELETE CASCADE

-- 任务关联
FOREIGN KEY (session_task_id) REFERENCES u2a_session_tasks(id)
    ON DELETE CASCADE  -- Memory 表
    ON DELETE SET NULL -- Message 表（保留消息但清除任务关联）
```

---

## 触发器设计

Message 表配置了自动更新时间戳的触发器：

```sql
-- 插入/更新时自动更新 updated_at
CREATE TRIGGER *_before_insert/update ...

-- 插入/更新时同步更新会话的 updated_at
CREATE TRIGGER *_after_insert/update ...
```

---

## 数据生命周期

| 表 | 生命周期 | 清理策略 |
|----|---------|---------|
| Message 表 | 永久保存 | 手动清理 |
| Memory 表 | 短期使用 | 定期压缩 |

---

## 总结

本数据库设计采用了**关注点分离**原则：

1. **Message 表**: 面向业务，管理消息状态和生命周期
2. **Memory 表**: 面向 AI，构建 LLM 对话上下文
3. **两层序列索引**: 用户消息全局排序，Agent 消息任务内排序

这种设计使得业务逻辑和 AI 模型交互可以独立演进，互不影响。
