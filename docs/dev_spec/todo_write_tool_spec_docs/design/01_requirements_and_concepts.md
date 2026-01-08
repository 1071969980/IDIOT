---
文档标题：概念设计 - 需求分析与核心概念
文档描述：描述 TODO Write 工具的需求分析、核心概念定义（包括 Todo 数据模型、状态管理、标签系统等）。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发开发文档之外的文件时,尽量使用相对于项目根目录的相对路径
---

**目录**:
- [需求分析](#需求分析)
- [核心概念定义](#核心概念定义)

## 需求分析

### 问题背景

在 LLM 多轮对话场景中，Agent 需要跟踪和管理任务状态。例如：

1. **任务分解**：用户提出一个复杂任务，Agent 将其分解为多个子任务
2. **进度跟踪**：Agent 需要记录哪些任务已完成、哪些进行中、哪些待办
3. **上下文记忆**：在多轮对话中保持对任务状态的记忆
4. **状态恢复**：会话中断后能够恢复之前的任务状态

### 需求定位

**todo_write 工具的定位**：
- **不是传统的任务管理应用**：不需要截止日期提醒、团队协作等功能
- **LLM 内部状态管理工具**：帮助 Agent 在对话过程中管理自己的任务状态
- **写操作专用工具**：只提供创建、更新、删除功能，读取由其他机制负责

### 核心需求

1. **CRUD 操作**：支持创建、读取、更新、删除 TODO（但工具层只暴露写操作）
2. **灵活存储**：支持不同存储后端（session_storage、memory、自定义）
3. **会话隔离**：TODO 与 session 绑定，不同 session 的 TODO 相互独立
4. **状态管理**：支持 pending/in_progress/completed/cancelled 状态流转
5. **标签系统**：支持为 TODO 添加标签，便于组织和分类
6. **优先级管理**：支持优先级字段，帮助 Agent 决策执行顺序
7. **可测试性**：支持依赖注入，便于单元测试

### 非需求

- ❌ 不需要用户界面（纯后端工具）
- ❌ 不需要跨会话共享 TODO（会话隔离）
- ❌ 不需要复杂的权限管理（session 隔离已足够）
- ❌ 不需要实时通知功能
- ❌ 工具层不需要读取功能（由其他机制提供）

## 核心概念定义

### Todo 数据模型

#### 基本字段

| 字段名 | 类型 | 必需 | 说明 |
|--------|------|------|------|
| `id` | string (UUID) | 是 | Todo 的唯一标识符，使用 UUID v4 格式 |
| `title` | string | 是 | Todo 的标题，简短描述 |
| `description` | string \| null | 否 | Todo 的详细描述 |
| `status` | string | 是 | Todo 状态，可选值见下方 |
| `priority` | integer | 是 | 优先级，数值越大优先级越高，默认 0 |
| `tags` | string[] | 是 | 标签列表，默认为空数组 `[]` |
| `created_at` | string (ISO 8601) | 是 | 创建时间 |
| `updated_at` | string (ISO 8601) | 是 | 最后更新时间 |

#### 状态枚举

Todo 支持 4 种状态：

```python
TodoStatus = Literal["pending", "in_progress", "completed", "cancelled"]
```

| 状态值 | 含义 | 使用场景 |
|--------|------|----------|
| `pending` | 待办 | 新创建的 TODO，尚未开始处理 |
| `in_progress` | 进行中 | Agent 正在处理该 TODO |
| `completed` | 已完成 | TODO 已完成 |
| `cancelled` | 已取消 | TODO 不再需要，被取消 |

#### 状态流转规则

```
pending
   │
   ├──→ in_progress
   │        │
   │        ├──→ completed
   │        │
   │        └──→ cancelled
   │
   └──→ cancelled
```

**流转规则**：
1. `pending` 可流转到 `in_progress` 或 `cancelled`
2. `in_progress` 可流转到 `completed` 或 `cancelled`
3. `completed` 和 `cancelled` 是终态，不可再流转
4. 默认不允许从 `pending` 直接流转到 `completed`（必须经过 `in_progress`）
   - 可通过 `TodoWriteConfig.enforce_status_transitions=False` 关闭此验证
   - 关闭后允许任意状态流转

### 标签系统设计

标签用于组织和分类 TODO，便于 Agent 理解和筛选。

#### 标签的设计原则

1. **扁平化**：不支持标签层级，使用扁平的字符串数组
2. **多标签**：一个 TODO 可以有多个标签
3. **标准化**：建议使用小写、连字符分隔的命名方式

#### 推荐的标签类别

| 类别 | 标签示例 | 用途 |
|------|----------|------|
| 任务类型 | `coding`, `research`, `review`, `testing` | 标识任务类型 |
| 优先级标记 | `urgent`, `important`, `routine` | 标识重要程度 |
| 阶段标记 | `phase-1`, `phase-2`, `milestone` | 标识阶段 |
| 功能模块 | `auth`, `database`, `ui` | 标识功能模块 |

#### 标签使用示例

```json
{
  "id": "01234567-89ab-cdef-0123-456789abcdef",
  "title": "实现用户认证功能",
  "status": "in_progress",
  "tags": ["coding", "urgent", "auth", "phase-1"]
}
```

### 优先级机制

优先级使用整数表示，数值越大优先级越高。

| 优先级值 | 含义 | 使用建议 |
|----------|------|----------|
| `< 0` | 低优先级 | 可延后处理的任务 |
| `0` | 默认优先级 | 普通任务 |
| `1-5` | 中等优先级 | 需要关注的任务 |
| `6-10` | 高优先级 | 重要且紧急的任务 |
| `> 10` | 最高优先级 | 阻塞性任务，必须立即处理 |

### 数据在 Session Storage 中的组织

TODO 数据存储在 `u2a_session_storage.storage` JSONB 字段中：

```json
{
  "todos": [
    {
      "id": "01234567-89ab-cdef-0123-456789abcdef",
      "title": "完成代码审查",
      "description": "审查 PR #123 的代码变更",
      "status": "in_progress",
      "priority": 5,
      "tags": ["review", "urgent"],
      "created_at": "2025-01-08T10:00:00Z",
      "updated_at": "2025-01-08T10:30:00Z"
    },
    {
      "id": "01234567-89ab-cdef-0123-456789abcdff",
      "title": "编写单元测试",
      "description": "为新功能编写单元测试",
      "status": "pending",
      "priority": 3,
      "tags": ["testing", "coding"],
      "created_at": "2025-01-08T11:00:00Z",
      "updated_at": "2025-01-08T11:00:00Z"
    }
  ]
}
```

**数据结构说明**：
- 根键 `"todos"` 是固定的
- 值是 TODO 对象数组
- 每个 TODO 对象包含完整的字段信息

---

**下一步**：请参考 [`02_architecture_and_config.md`](./02_architecture_and_config.md) 了解架构设计和 Config 设计。
