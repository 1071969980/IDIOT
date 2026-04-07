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
| `u2a_session_tasks` | 会话任务记录（树形结构） |
| `u2a_session_branches` | 会话分支指针（类似 git HEAD） |

---

## 树形结构与分支

### 设计背景

session_task 从线性结构改为**树形结构**，并引入 **Branch（分支）** 概念，使用户可以像 git 一样在对话的不同方向间切换。

### 树形 Session Task

每个 task 记录其父节点（`parent_task_id`）和 ltree 路径（`tree_path`），形成一棵树。

```
Session
│
├─ Task 0 (root, seq=0, path='t0')
│   │
│   ├─ Task 1 (seq=1, path='t0.t1')
│   │   ├─ Task 3 (seq=3, path='t0.t1.t3')  ← Branch "main"
│   │   └─ Task 4 (seq=4, path='t0.t1.t4')  ← Branch "alt"
│   │
│   └─ Task 2 (seq=2, path='t0.t2')          ← Branch "try-again"
```

- `seq_in_session`：session 内自增序号，用于 ltree label 和展示序号
- `tree_path`：ltree 类型路径，用 `'t' || seq_in_session` 作为 label（ltree label 必须以字母开头）

### Branch（分支）

Branch 是一个**指针**，类似 git HEAD，指向当前叶子 task。每个叶子 task 与 Branch 是一对一关系。

- Branch 表有 `leaf_task_id` 字段记录指向的叶子 task（**无 FK 约束**，避免循环依赖）
- Task 表有 `branch_id` 字段记录所属 Branch（**有 FK 约束**，仅叶子节点非空）

### context_breakpoints（上下文断点）

`context_breakpoints` 是 `INT[]` 类型的字段，记录 task 内 Agent 短期记忆发生上下文压缩的位置。

- 值的含义：压缩后有效记忆的起始 sub_index，截取时包含该值本身
- 用途一：实际业务逻辑只使用 `context_breakpoints[-1]` 确定从哪个 sub_index 开始截取
- 用途二：完整 list 用于审计，追踪多次压缩的历史
- 默认值为空数组 `[]`，表示无压缩发生

### `u2a_session_tasks` 字段说明

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | UUID | PK DEFAULT uuidv7() | |
| `session_id` | UUID | NOT NULL, FK -> u2a_sessions(id) ON DELETE CASCADE | |
| `user_id` | UUID | NOT NULL, FK -> simple_users(id) ON DELETE CASCADE | |
| `status` | VARCHAR(32) | NOT NULL, CHECK IN ('pending', 'processing', 'completed', 'failed', 'cancelled') | |
| `parent_task_id` | UUID | NULL, FK -> u2a_session_tasks(id) ON DELETE CASCADE | 父节点，root 为 NULL |
| `branch_id` | UUID | NULL, FK -> u2a_session_branches(id) ON DELETE SET NULL | 仅叶子节点记录 |
| `seq_in_session` | INT | NOT NULL DEFAULT 0 | session 内自增序号 |
| `tree_path` | ltree | NOT NULL | 树路径（使用 GIST 索引） |
| `context_breakpoints` | INT[] | DEFAULT '{}' | 上下文压缩断点列表 |
| `storage_snapshot` | JSONB | DEFAULT NULL | 任务特定存储数据，沿树继承（查询最近非空祖先） |
| `logic_mark` | JSONB | DEFAULT NULL | 程序逻辑控制标记，支持按字段名查找最近祖先（使用 `?` 操作符） |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | |
| `updated_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | |

### `u2a_session_branches` 字段说明

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | UUID | PK DEFAULT uuidv7() | |
| `session_id` | UUID | NOT NULL, FK -> u2a_sessions(id) ON DELETE CASCADE | |
| `name` | VARCHAR(255) | NOT NULL, UNIQUE(session_id, name) | session 内唯一 |
| `created_by` | VARCHAR(32) | NOT NULL, CHECK IN ('user', 'agent', 'system') | 创建者 |
| `archived` | BOOLEAN | DEFAULT FALSE | 是否归档 |
| `leaf_task_id` | UUID | NOT NULL | 指向叶子 task（无 FK 约束） |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | |
| `updated_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | |

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

### 3. `seq_in_session` (任务序列索引)

**作用范围**: 会话级别 (`session_id`)

**应用表**: `u2a_session_tasks`

**递增规则**:
```sql
SELECT COALESCE(MAX(seq_in_session), -1) + 1
WHERE session_id = :session_id
```

**设计目的**:
- 为会话内的所有 task 提供全局唯一的递增序号
- 作为 ltree label 的基础（`'t' || seq_in_session`）
- 支持按插入顺序的排序和展示

---

### 4. 两层序列架构

```
会话 (Session)
│
├─ Task A (用户 seq_index: 0-1)
│   ├─ 用户消息 1 (seq_index: 0)        ← 任务开始时的一组用户消息
│   ├─ 用户消息 2 (seq_index: 1)
│   ├─ Agent 消息 1 (sub_seq_index: 0)  ← Agent 响应组
│   └─ Agent 消息 2 (sub_seq_index: 1)
│
└─ Task B (用户 seq_index: 2-3)
    ├─ 用户消息 3 (seq_index: 2)        ← 新任务的一组用户消息
    ├─ Agent 消息 1 (sub_seq_index: 0)  ← 新任务从 sub_seq_index=0 重新开始
    └─ Agent 消息 2 (sub_seq_index: 1)
```

**设计优势**:
- 用户消息具有全局时序，便于跨任务查询
- Agent 消息按任务局部排序，反映任务内部的逻辑流
- 每个任务内遵循严格的顺序：先所有用户消息，再所有 Agent 消息

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
    ├─ u2a_session_branches (分支指针)
    │       └─ leaf_task_id -> u2a_session_tasks (无 FK)
    │
    └─ u2a_session_tasks (任务，树形结构)
            │
            ├─ parent_task_id -> u2a_session_tasks (自引用, ON DELETE CASCADE)
            ├─ branch_id -> u2a_session_branches (ON DELETE SET NULL, 仅叶子节点)
            │
            ├─ u2a_user_messages (用户消息)
            │       └─ seq_index: 全局递增
            │
            ├─ u2a_agent_messages (Agent消息)
            │       └─ sub_seq_index: 任务内递增
            │
            ├─ u2a_user_short_term_memory (用户记忆)
            │       └─ seq_index: 全局递增
            │
            └─ u2a_agent_short_term_memory (Agent记忆)
                    └─ sub_seq_index: 任务内递增
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

### 树形结构专用索引

```sql
-- ltree 路径查询（支持祖先/后代查询）
CREATE INDEX idx_u2a_session_tasks_tree_path ON u2a_session_tasks USING GIST (tree_path);

-- 父子关系查询
CREATE INDEX idx_u2a_session_tasks_parent_task_id ON u2a_session_tasks (parent_task_id);

-- 分支关联查询
CREATE INDEX idx_u2a_session_tasks_branch_id ON u2a_session_tasks (branch_id);

-- 任务 storage JSONB 查询
CREATE INDEX idx_u2a_session_tasks_storage_snapshot ON u2a_session_tasks USING GIN (storage_snapshot);

-- 任务逻辑标记 JSONB 查询（支持 ? / ?| / ?& / @> 操作符）
CREATE INDEX idx_u2a_session_tasks_logic_mark ON u2a_session_tasks USING GIN (logic_mark);

-- 分支叶子任务查询
CREATE INDEX idx_u2a_session_branches_leaf_task_id ON u2a_session_branches (leaf_task_id);
```

### 查询模式优化

- **按会话查询**: 使用 `session_id` 索引，按序列索引排序
- **按任务查询**: 使用 `session_task_id` 索引，按子序列索引排序
- **分页查询**: 利用序列索引的范围查询
- **分支路径查询**: 使用递归 CTE 沿 parent_task_id 遍历树

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

-- 树形结构关联
FOREIGN KEY (parent_task_id) REFERENCES u2a_session_tasks(id) ON DELETE CASCADE  -- 级联删除子节点
FOREIGN KEY (branch_id) REFERENCES u2a_session_branches(id) ON DELETE SET NULL  -- 分支删除时置空

-- 注意: branch.leaf_task_id 不设 FK 约束（与 task.branch_id 形成引用环，由应用层保证一致性）
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

Branch 表同样配置了 `updated_at` 自动更新触发器。

---

## 数据生命周期

| 表 | 生命周期 | 清理策略 |
|----|---------|---------|
| Message 表 | 永久保存 | 手动清理 |
| Memory 表 | 短期使用 | 定期压缩 |
| Branch 表 | 随会话 | 会话删除时级联删除 |

---

## 总结

本数据库设计采用了**关注点分离**原则：

1. **Message 表**: 面向业务，管理消息状态和生命周期
2. **Memory 表**: 面向 AI，构建 LLM 对话上下文
3. **两层序列索引**: 用户消息全局排序，Agent 消息任务内排序
4. **树形任务结构**: 支持对话分支和回溯，使用 ltree 实现高效路径查询
5. **Branch 指针**: 类似 git HEAD 的机制，支持在多个对话方向间切换

这种设计使得业务逻辑和 AI 模型交互可以独立演进，互不影响。
