# SessionAgentConfig 关键字段分析报告

> 分析对象：`allowed_rel_dirs_in_juicefs_for_tool`、`user_permission_role`、`user_id_for_scope`
> 分析日期：2026-06-08

---

## 0. 长期目标：移除共享字段，下沉至工具级 Config

将 `SessionAgentConfig` 中的 `allowed_rel_dirs_in_juicefs_for_tool`、`user_id_for_scope` 以及 `ToolFactory` 中的 `user_permission_role` 逐步移除。这些字段的语义差异很大，不该作为所有工具的共享配置，而应下沉到每个工具各自的 `ToolConfig` 中，由工具自行定义和消费。

迁移策略：逐工具改造。每完成一个工具的改造，该工具对共享字段的依赖即解除。当所有工具都完成迁移后，从 `SessionAgentConfig` 和 `ToolFactory` 中移除这些字段。

### 改造进度

| 工具 | 状态 | 说明 |
|------|------|------|
| load_skill | Issue #2 已完成 | `SkillToolScope`，scope_def + resolve_scope_value 范式 |
| unload_skill | 确认无需改动 | 不需要 scope，只操作 storage_snapshot |
| read_file | Issue #3 已完成 | `FileOpsToolScope`，kwargs 组装范式，W/B 路径校验 |
| edit_file | Issue #3 已完成 | 同上 |
| write_file | Issue #3 已完成 | 同上 |
| list_directory | Issue #3 已完成 | 同上 |
| delete_file | Issue #3 已完成 | 同上 |
| move_file | Issue #3 已完成 | 同上 |
| copy_file | Issue #3 已完成 | 同上，同时修复 `work_dirs` bug |
| bash | 待改造 | |
| todo | 待改造 | |
| memory_recall | 待改造 | JuiceFSSdkBackend 直接构造需迁移 |
| memory_write | 待改造 | 同上 |

### 设计决策

**1. 每个工具定义自己的 scope 模型。** 不同工具对 scope 的语义需求不同，不复用同一个 `ToolScope` 类型。例如 load_skill 的 scope 包含 `user_id_for_scope`、`role`、`proj_path`；而文件操作工具的 scope 可能完全不同。

**2. scope 默认值为 `None`，由构造函数在运行时填充。** 持久化配置中 `tool_scope=None`，`construct_*` 函数从 kwargs 取原始数据组装 scope 对象并写入 config。ToolFactory 不感知 scope 构造逻辑。

**3. scope 构造优先级：先查预构造参数，再走组装。** 所有工具的 `construct_*` 统一遵循：① 若 kwargs 中存在预构造的 scope 参数（如 `load_skill_tool_scope`），直接使用；② 否则从 kwargs 的独立字段组装 scope 对象；③ 组装失败则 raise。

**4. scope 构造失败时 raise，不允许工具在无 scope 状态下运行。**

---

## 1. 字段概览

三个字段均定义在 `api/agent/session_agent_config/config_data_model.py` 的 `SessionAgentConfig` 中：

```python
class SessionAgentConfig(BaseModel):
    allowed_rel_dirs_in_juicefs_for_tool: list[PurePosixPath]
    user_id_for_scope: UUID | None = None
    # user_permission_role 不在此处定义，定义在 tool_factory.py 中
```

`user_permission_role` 定义在 `api/agent/tools/tool_factory/tool_factory.py`：

```python
class UserToolCallingPermissionRole(str, Enum):
    OWNER = "owner"
    VISITOR = "visitor"
```

| 字段 | 类型 | 默认值 | 实现状态 |
|------|------|--------|---------|
| `allowed_rel_dirs_in_juicefs_for_tool` | `list[PurePosixPath]` | `[PurePosixPath("./")]` | 已实现，核心生效中 |
| `user_id_for_scope` | `UUID \| None` | `None` → fallback 到 `user_id` | 已实现，默认退化为当前用户 |
| `user_permission_role` | `UserToolCallingPermissionRole` | 硬编码 `OWNER` | 部分实现：VISITOR 角色用于文件操作隐藏路径过滤 |

---

## 2. allowed_rel_dirs_in_juicefs_for_tool

### 2.1 作用

JuiceFS 文件系统的**沙箱边界控制**，决定 agent 可以读写哪些目录。同时是**记忆系统是否激活的开关**。

### 2.2 数据流

```
SessionAgentConfig.allowed_rel_dirs_in_juicefs_for_tool
    │
    ├─→ process_pending_messages.py:199 ─→ init_tools() ─→ ToolFactory
    │       (启动时读取配置)
    │
    ├─→ tool_init.py:58 ─→ ToolInitializationResult.allowed_rel_dirs_in_juicefs_for_tool
    │       (聚合为 set，支持多个工具 init 结果合并)
    │
    └─→ 各工具 constructor 通过 kwargs 接收
            └─→ JuiceFSSdkBackend.__init__()
```

### 2.3 影响范围

#### 2.3.1 文件操作工具的路径访问控制（核心作用）

`JuiceFSSdkBackend._check_work_dir_access()`（`juicefs_sdk.py`）在每次文件操作前校验。Issue #3 改造后使用 `FileOpsToolScope` 的 W/B + Role 组合逻辑：

1. **VISITOR 隐藏路径检查**：遍历 `rel_path.parts`，任一以 `.` 开头则拒绝
2. **黑名单检查**：路径在任何 B 目录下则拒绝
3. **白名单检查**：W 为空则允许，否则路径须在某个 W 目录下

四种场景：空 W+空 B=全放行 | 仅 W=白名单 | 仅 B=黑名单 | W+B=交集

受约束的工具清单（7 个，均使用 `FileOpsToolScope`）：

| 工具 | 构造函数文件 |
|------|-------------|
| read_file | `file_operations/read_file/constructor.py` |
| edit_file | `file_operations/edit_file/constructor.py` |
| write_file | `file_operations/write_file/constructor.py` |
| list_directory | `file_operations/list_directory/constructor.py` |
| delete_file | `file_operations/delete_file/constructor.py` |
| move_file | `file_operations/move_file/constructor.py` |
| copy_file | `file_operations/copy_file/constructor.py` |

#### 2.3.2 记忆系统的触发判断

`main_agent_strategy.py` 的三阶段流程依赖此字段判断记忆系统是否激活：

- **记忆召回** — `_has_valid_memory_indices()`（line 44-78）：检查 `allowed_rel_dirs` 中是否包含 `sys/memory/` 子路径且对应目录下存在 `MEMORY.md` 文件
- **记忆写入** — `_should_run_memory_write()`（line 81-90）：检查是否包含 `sys/memory/` 子路径
- **memory_recall/memory_discovery.py** 和 **memory_write/memory_discovery.py**：从允许路径中发现并读取 `MEMORY.md`

判断逻辑：遍历 `allowed_rel_dirs_in_juicefs_for_tool`，尝试将每个路径解析为 `sys/memory` 的子路径（`PurePosixPath.relative_to(memory_root)`），成功则该路径参与记忆操作。

#### 2.3.3 项目管理命令的动态修改

通过 storage_snapshot overlay 机制，在运行时动态修改当前 session 分支的 `allowed_rel_dirs_in_juicefs_for_tool`：

| 操作 | 文件 | 行为 |
|------|------|------|
| create_project | `command/project/create/command.py:36` | 添加 `project_path` 和可选的 `memory_path` |
| delete_project | `command/project/delete/command.py:31` | 移除 `project_path` 和对应 `memory_path` |
| create_memory | `command/project/create_memory/command.py:33` | 为已有项目追加 `memory_path` |
| exists_project | `command/project/exists/command.py:33` | 检查路径是否已在列表中 |

#### 2.3.4 MCP 工具

`mcp/adapter.py:115` 传入空集合 `set()`。MCP 工具不访问 JuiceFS，无需路径权限。

### 2.4 默认值

`constants.py:86`：默认值为 `[PurePosixPath("./")]`，即允许访问用户 JuiceFS 根目录下的所有路径。

---

## 3. user_id_for_scope

### 3.1 作用

区分"请求发起者"和"资源作用域归属"，支持**跨用户协作场景**。

| 字段 | 含义 | 用途 |
|------|------|------|
| `user_id` | 请求发起者（谁在调用） | 日志追踪、审计 |
| `user_id_for_scope` | 资源作用域归属（操作谁的数据） | 存储隔离、容器归属 |

### 3.2 数据流

```
SessionAgentConfig.user_id_for_scope
    │
    ├─→ process_pending_messages.py:189
    │       user_id_for_scope = session_config.user_id_for_scope or user_id
    │       (None 时 fallback 到 user_id，即自己操作自己)
    │
    └─→ ToolFactory.__init__() ─→ prepare_tool() ─→ 各工具 constructor
            通过 kwargs["user_id_for_scope"] 传递
```

### 3.3 影响范围

#### 3.3.1 JuiceFS 文件操作工具 — 多租户存储隔离

所有 7 个文件操作工具在构造 `JuiceFSSdkBackend` 时，使用 `user_id_for_scope` 派生 JuiceFS 租户信息：

```python
# juicefs_sdk.py:61-62
self.meta_url = get_meta_url(str(user_id))   # 元数据连接 URL
self.pvc_name = get_pvc_name(str(user_id))   # PVC 名称前缀
```

**效果**：agent 访问的是 `user_id_for_scope` 指向的用户的 JuiceFS 存储，而非请求者的存储。

#### 3.3.2 Bash 工具 — 用户容器归属

`bash/constructor.py:212`：用 `user_id_for_scope` 确定命令在哪个用户的 pod 中执行。

```python
async with pod_command_session(
    user_id=self.user_id,        # ← 来自 user_id_for_scope
    image=self.config.image,
    ...
) as session:
```

#### 3.3.3 Todo 工具 — 存储快照作用域

`todo/constructor.py:289-292`：传入 `StorageSnapshotTodoBackend`，决定 todo 数据归属哪个用户的存储快照。

#### 3.3.4 Skills 工具 — 用户级 skill 配置

`load_skill/constructor.py:127` 和 `unload_skill/constructor.py:100`：用 `user_id_for_scope` 确定从哪个用户的配置中加载/卸载 skill。

### 3.4 当前状态

`config_data_model.py:104` 定义默认值为 `None`。`process_pending_messages.py:189` 中 `None` 时退化为 `user_id`（自己操作自己）。当前所有场景均为退化状态，但跨用户操作的通道已完整预留。

---

## 4. user_permission_role

### 4.1 作用（设计意图）

为未来多用户协作场景下的**工具调用权限分级**。从枚举值推测：

| 枚举值 | 预期含义 |
|--------|---------|
| `OWNER` | 资源所有者，拥有完全操作权限 |
| `VISITOR` | 访客，不允许访问隐藏路径（以 `.` 开头的路径组件） |

`VISITOR_AGENT` 已在 Issue #3 中移除，无任何消费者。

### 4.2 数据流

```
process_pending_messages.py:198
    user_permission_role=UserToolCallingPermissionRole.OWNER  # 硬编码
        │
        └─→ ToolFactory.__init__() ─→ prepare_tool() ─→ 各工具 constructor
                通过 kwargs["user_permission_role"] 传递
                    │
                    └─→ 未被任何工具消费
```

### 4.3 实现状态

**未实现。** 完整调用链中没有任何工具构造函数或工具类读取或使用此参数。

数据流路径：
1. `process_pending_messages.py:198` — 唯一写入点，硬编码 `OWNER`
2. `tool_init.py:29` — 函数签名接收
3. `tool_factory.py:38` — 存储为实例属性
4. `tool_factory.py:61,75` — 传入各工具构造函数的 `**kwargs`
5. **没有任何工具从 kwargs 中取出此值**

### 4.4 与其他字段的关系

与 `user_id_for_scope` 共同构成多用户协作权限体系的两个维度：

```
user_id_for_scope  →  "操作谁的数据"  （已实现）
user_permission_role → "能做什么操作"  （未实现）
```

要使多用户协作完整生效，两个字段需要同时配置：
- `user_id_for_scope` 指向目标用户的资源
- `user_permission_role` 限制操作者的权限级别

---

## 5. 三个字段的协作关系

```
┌──────────────────────────────────────────────────────────────┐
│                    多用户协作权限体系                          │
│                                                              │
│  user_id_for_scope          user_permission_role             │
│  ┌─────────────────┐       ┌─────────────────────┐          │
│  │ 资源归属维度      │       │ 操作权限维度          │          │
│  │                 │       │                     │          │
│  │ "操作谁的数据"    │       │ "能做什么操作"        │          │
│  │ 已实现 ✓         │       │ 未实现 ✗             │          │
│  └────────┬────────┘       └──────────┬──────────┘          │
│           │                            │                     │
│           └────────────┬───────────────┘                     │
│                        ▼                                     │
│     allowed_rel_dirs_in_juicefs_for_tool                     │
│     ┌─────────────────────────────────┐                     │
│     │ 路径沙箱维度                      │                     │
│     │                                 │                     │
│     │ "可以在哪些目录操作"              │                     │
│     │ 已实现 ✓                         │                     │
│     └─────────────────────────────────┘                     │
│                                                              │
│  三者结合：                                                   │
│  用户 A 访问用户 B 的 /project_x 目录，以 VISITOR 身份只读     │
│  （需要 user_id_for_scope=B, permission=VISITOR,             │
│   allowed_dirs=[/project_x]）                                │
└──────────────────────────────────────────────────────────────┘
```

---

## 6. 附录：关键文件索引

| 文件 | 关键内容 |
|------|---------|
| `api/agent/session_agent_config/config_data_model.py` | `SessionAgentConfig` 模型定义（`allowed_rel_dirs_in_juicefs_for_tool`、`user_id_for_scope`） |
| `api/agent/session_agent_config/constants.py` | 默认配置值 |
| `api/agent/tools/tool_factory/tool_factory.py` | `UserToolCallingPermissionRole` 枚举、`ToolFactory` 工厂类 |
| `api/chat/data_model.py` | `ToolInitializationResult` 数据类 |
| `api/chat/tool_init.py` | `init_tools()` 工具初始化入口 |
| `api/app/chat/process_pending_messages.py` | 消息处理主流程，三个字段的唯一赋值入口 |
| `api/agent/tools/file_operations/storage_backend/juicefs_sdk.py` | JuiceFS 存储后端，`FileOpsToolScope` W/B 路径校验实现 |
| `api/agent/tools/file_operations/config_scope_data_model.py` | `FileOpsToolScope` 模型、`assemble_file_ops_scope_from_kwargs` 组装函数、`FILE_OPS_*_PATHS` 常量 |
| `api/agent/strategy/main_agent_strategy.py` | 主 agent 策略，记忆系统依赖 `allowed_rel_dirs` |
| `api/app/chat/session_agent_config/command/project/` | 项目管理命令，动态修改 `allowed_rel_dirs` |
| `api/agent/tools/memory_recall/memory_discovery.py` | 记忆召回，从 `allowed_rel_dirs` 发现记忆文件 |
| `api/agent/tools/memory_write/memory_discovery.py` | 记忆写入，从 `allowed_rel_dirs` 发现记忆文件 |

---

## scope_def 改造范式

### 核心思路

将 `allowed_rel_dirs_in_juicefs_for_tool`、`user_id_for_scope`、`user_permission_role` 三个共享字段从 `SessionAgentConfig` 顶层移入 `scope_def: dict[str, Any] = {}` 字典。`scope_def` 在创建 session 时被填充，后续可通过 overlay 机制覆盖。

### 数据流

```
create_session (填充 scope_def)
  → SessionAgentConfig.scope_def
    → process_pending_messages (提取 scope_def)
      → init_tools(scope_def=scope_def)
        → ToolFactory(scope_def=scope_def)
          → construct_*_tool(config, scope_def, **kwargs)
            → resolve_scope_value(scope_def, FIELD_PATHS)  # 解析各字段
```

### 工具解析规范

1. 每个工具在对应的 `config_data_model.py` 中声明模块级常量（非类内 ClassVar），命名格式 `<TOOL>_<FIELD>_PATHS`，值为字符串列表，按优先级排列，支持点号分隔的嵌套路径：

```python
# api/agent/tools/skills/load_skill/config_data_model.py
LOAD_SKILL_USER_ID_PATHS: list[str] = ["user_id_for_scope"]
LOAD_SKILL_ROLE_PATHS: list[str] = ["user_permission_role"]
LOAD_SKILL_PROJ_PATHS: list[str] = ["allowed_rel_dirs_in_juicefs_for_tool"]
```

2. 使用 `api/agent/session_agent_config/utils.py` 中的 `resolve_scope_value(scope_def, key_paths)` 解析，依次尝试 key_paths 中的每个路径，返回第一个找到的值，全部未找到时抛出 KeyError。

3. 构造器优先级：
   - 优先级 1：`config.tool_scope` 已有（从 overlay 或持久化配置恢复）
   - 优先级 2：从 `scope_def` 通过 `resolve_scope_value` 解析

### 已迁移的工具

| 工具 | ToolScope 模型 | 范式 | Scope Key 常量文件 |
|------|---------------|------|-------------------|
| load_skill | `SkillToolScope` | scope_def + resolve_scope_value | `api/agent/tools/skills/load_skill/config_data_model.py` |
| read_file | `FileOpsToolScope` | kwargs 组装 + 共享函数 | `api/agent/tools/file_operations/config_scope_data_model.py` |
| edit_file | `FileOpsToolScope` | 同上 | 同上 |
| write_file | `FileOpsToolScope` | 同上 | 同上 |
| list_directory | `FileOpsToolScope` | 同上 | 同上 |
| delete_file | `FileOpsToolScope` | 同上 | 同上 |
| move_file | `FileOpsToolScope` | 同上 | 同上 |
| copy_file | `FileOpsToolScope` | 同上 | 同上 |

## 本次改造被破坏的功能

以下功能因直接引用 `SessionAgentConfig.allowed_rel_dirs_in_juicefs_for_tool`（已移除）而暂时不可用，需后续迁移至从 `scope_def` 读取：

| 文件 | 功能 |
|------|------|
| `api/app/chat/session_agent_config/command/project/create/command.py` | 创建项目（读取 `effective_config.allowed_rel_dirs_in_juicefs_for_tool`） |
| `api/app/chat/session_agent_config/command/project/delete/command.py` | 删除项目 |
| `api/app/chat/session_agent_config/command/project/exists/command.py` | 检查项目是否存在 |
| `api/app/chat/session_agent_config/command/project/create_memory/command.py` | 创建项目记忆 |

以下位置因 `JuiceFSSdkBackend.__init__` 签名变更为 `scope: FileOpsToolScope` 而编译失败，需迁移至使用 `FileOpsToolScope`：

| 文件 | 功能 |
|------|------|
| `api/agent/strategy/main_agent_strategy.py:66` | 记忆系统，直接构造 JuiceFSSdkBackend |
| `api/agent/tools/memory_recall/memory_discovery.py:23` | 记忆召回，`_get_juicefs_backend` 辅助函数 |
| `api/agent/tools/memory_write/memory_discovery.py:23` | 记忆写入，`_get_juicefs_backend` 辅助函数 |

以下工具尚未迁移，仍从 kwargs 读取旧字段：

| 工具 | 构造器文件 |
|------|-----------|
| bash | `api/agent/tools/bash/constructor.py` |
| sub_agent | `api/agent/tools/sub_agent/constructor.py` |
