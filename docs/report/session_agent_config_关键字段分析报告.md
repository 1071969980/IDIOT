# SessionAgentConfig 关键字段分析报告

> 分析对象：`allowed_rel_dirs_in_juicefs_for_tool`、`user_permission_role`、`user_id_for_scope`
> 分析日期：2026-06-08
> 最后更新：2026-06-11（Issue #4 完成后更新）

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
| memory_recall | Issue #4 已完成 | `MemoryToolScope`，独立工具构造，目录合并至 `memory/recall/` |
| memory_write | Issue #4 已完成 | 同上，目录合并至 `memory/write/` |
| bash | Issue #5 已完成 | `BashToolScope`，scope_def + resolve_scope_value 范式 |
| todo | 确认无需改动 | 与 session 绑定（session_id/branch_name/user_id），非 scope 概念 |

### 设计决策

**1. 每个工具定义自己的 scope 模型。** 不同工具对 scope 的语义需求不同，不复用同一个 `ToolScope` 类型。例如 load_skill 的 scope 包含 `user_id_for_scope`、`role`、`proj_path`；而文件操作工具的 scope 可能完全不同。

**2. scope 默认值为 `None`，由构造函数在运行时填充。** 持久化配置中 `tool_scope=None`，`construct_*` 函数从 kwargs 取原始数据组装 scope 对象并写入 config。ToolFactory 不感知 scope 构造逻辑。

**3. scope 构造优先级：先查预构造参数，再走组装。** 所有工具的 `construct_*` 统一遵循：① 若 config.tool_scope 已有（预构造或持久化恢复），直接使用；② 否则从 `scope_def` 通过 `resolve_scope_value` 解析。

**4. scope 构造失败时 raise，不允许工具在无 scope 状态下运行。**

**5. 记忆 Agent 独立工具构造（Issue #4）。** 记忆 Agent 不经过 `init_tools` / `ToolFactory`，在 `main_agent_strategy` 中直接调用工具构造器，拥有独立的 `ToolInitializationResult`。`should_mem_recall` / `should_mem_write` 控制变量提升为带默认值的参数，`resolve_memory_scope` 仅在需要时调用。

---

## 1. 字段概览

`user_id_for_scope` 和 `user_permission_role` 已从 `SessionAgentConfig` 顶层移入 `scope_def` 字典（Issue #2）。`allowed_rel_dirs_in_juicefs_for_tool` 在 Issue #3 后仅作为 `scope_def` 的回退键保留。

```python
class SessionAgentConfig(BaseModel):
    scope_def: dict[str, Any] = {}
    # scope_def 包含: user_id_for_scope, user_permission_role,
    #                  allowed_rel_dirs_in_juicefs_for_tool 等
```

`user_permission_role` 定义在 `api/agent/tools/type.py`：

```python
class UserToolCallingPermissionRole(str, Enum):
    OWNER = "owner"
    VISITOR = "visitor"
```

| 字段 | scope_def 中的键 | 类型 | 实现状态 |
|------|-----------------|------|---------|
| `user_id_for_scope` | `user_id_for_scope` | `UUID` | 已实现，各工具从 scope_def 解析 |
| `user_permission_role` | `user_permission_role` | `UserToolCallingPermissionRole` | 文件操作/记忆工具已接入，bash/todo 待改造 |
| `allowed_rel_dirs_in_juicefs_for_tool` | `allowed_rel_dirs_in_juicefs_for_tool` | `list[PurePosixPath]` | 已实现，作为各 ToolScope 的白名单源 |

---

## 2. allowed_rel_dirs_in_juicefs_for_tool

### 2.1 作用

JuiceFS 文件系统的**沙箱边界控制**，决定 agent 可以读写哪些目录。同时是**记忆系统目录列表**的来源。

### 2.2 数据流

Issue #3 改造后，此字段不再作为 `ToolInitializationResult` 的共享字段传递，而是由各工具构造器从 `scope_def` 直接解析：

```
SessionAgentConfig.scope_def["allowed_rel_dirs_in_juicefs_for_tool"]
    │
    ├─→ init_tools() → ToolFactory(scope_def) → construct_*(config, scope_def, **kwargs)
    │       → resolve_scope_value(scope_def, FILE_OPS_ALLOWED_DIRS_PATHS)
    │       → FileOpsToolScope(white_list=...)
    │
    └─→ main_agent_strategy(scope_def)
            → resolve_memory_scope(scope_def)
            → MemoryToolScope(memory_dirs=...)
```

### 2.3 影响范围

#### 2.3.1 文件操作工具的路径访问控制（核心作用）

`JuiceFSSdkBackend._check_work_dir_access()`（`juicefs_sdk.py`）在每次文件操作前校验。使用 `FileOpsToolScope` 的 W/B + Role 组合逻辑：

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

#### 2.3.2 记忆系统（Issue #4 改造后）

记忆系统不再从 `ToolInitializationResult.allowed_rel_dirs_in_juicefs_for_tool` 读取，改为独立的 `MemoryToolScope`：

- `main_agent_strategy` 从 `scope_def` 解析 `MemoryToolScope`
- `MemoryToolScope.memory_dirs` 提供记忆目录列表
- `MemoryToolScope.to_file_ops_scope()` 转换为 `FileOpsToolScope` 供 `JuiceFSSdkBackend` 使用
- 记忆 Agent 拥有独立的 `ToolInitializationResult`，不与 MainAgent 共享

控制变量：`should_mem_recall` / `should_mem_write` 作为 `main_agent_strategy` 的参数，默认 `False`。

#### 2.3.3 项目管理命令（已移除）

项目管理命令（`command/project/`）已从代码库中移除，不再需要迁移至 scope_def。

### 2.4 默认值

`constants.py`：默认值为 `[PurePosixPath("./")]`，即允许访问用户 JuiceFS 根目录下的所有路径。

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
scope_def["user_id_for_scope"]
    │
    ├─→ init_tools() → ToolFactory(scope_def)
    │       → construct_*(config, scope_def, **kwargs)
    │           → resolve_scope_value(scope_def, *_USER_ID_PATHS)
    │
    └─→ main_agent_strategy(scope_def)
            → resolve_memory_scope(scope_def)
            → MemoryToolScope(user_id_for_scope=...)
```

### 3.3 影响范围

#### 3.3.1 JuiceFS 文件操作工具 — 多租户存储隔离

所有 7 个文件操作工具在构造 `JuiceFSSdkBackend` 时，使用 `FileOpsToolScope.user_id_for_scope` 派生 JuiceFS 租户信息。

#### 3.3.2 记忆工具 — Issue #4 改造后

记忆 Agent 通过 `MemoryToolScope.user_id_for_scope` 构造独立的存储后端实例。

#### 3.3.3 Bash 工具 — 用户容器归属（Issue #5 已完成）

`bash/constructor.py`：通过 `BashToolScope.user_id_for_scope` 确定命令在哪个用户的 pod 中执行。

#### 3.3.4 Todo 工具 — 存储快照作用域（确认无需迁移）

`todo/constructor.py`：与 session 绑定（session_id/branch_name/user_id），非 scope 概念，保持从 kwargs 读取。

#### 3.3.5 Skills 工具 — 用户级 skill 配置

`load_skill/constructor.py` 和 `unload_skill/constructor.py`：用 `user_id_for_scope` 确定从哪个用户的配置中加载/卸载 skill。

### 3.4 当前状态

从 `scope_def` 解析，`None` 时退化为 `user_id`（自己操作自己）。当前所有场景均为退化状态，但跨用户操作的通道已完整预留。

---

## 4. user_permission_role

### 4.1 作用

为多用户协作场景下的**工具调用权限分级**：

| 枚举值 | 含义 |
|--------|------|
| `OWNER` | 资源所有者，拥有完全操作权限 |
| `VISITOR` | 访客，不允许访问隐藏路径（以 `.` 开头的路径组件） |

### 4.2 数据流

```
scope_def["user_permission_role"]
    │
    ├─→ 文件操作工具: resolve_scope_value(scope_def, FILE_OPS_ROLE_PATHS)
    │       → FileOpsToolScope(role=...)
    │
    └─→ 记忆工具: resolve_scope_value(scope_def, MEMORY_ROLE_PATHS)
            → MemoryToolScope(role=...)
```

### 4.3 实现状态

**文件操作工具 + 记忆工具 + bash 已完成。** todo 不需要 role（与 session 绑定），无需迁移。

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
│  └────────┬────────┘       └──────────┬──────────┘          │
│           │                            │                     │
│           └────────────┬───────────────┘                     │
│                        ▼                                     │
│     allowed_rel_dirs_in_juicefs_for_tool                     │
│     ┌─────────────────────────────────┐                     │
│     │ 路径沙箱维度                      │                     │
│     │                                 │                     │
│     │ "可以在哪些目录操作"              │                     │
│     └─────────────────────────────────┘                     │
│                                                              │
│  三者通过 scope_def 统一传递，各工具按需解析为 ToolScope       │
└──────────────────────────────────────────────────────────────┘
```

---

## 6. 附录：关键文件索引

| 文件 | 关键内容 |
|------|---------|
| `api/agent/session_agent_config/config_data_model.py` | `SessionAgentConfig` 模型定义（含 `scope_def`） |
| `api/agent/session_agent_config/utils.py` | `resolve_scope_value` 解析工具 |
| `api/agent/session_agent_config/constants.py` | 默认配置值 |
| `api/agent/tools/type.py` | `UserToolCallingPermissionRole` 枚举 |
| `api/chat/data_model.py` | `ToolInitializationResult` 数据类（已移除 `allowed_rel_dirs`） |
| `api/chat/tool_init.py` | `init_tools()` 工具初始化入口 |
| `api/app/chat/process_pending_messages.py` | 消息处理主流程，传递 `scope_def` |
| `api/agent/tools/file_operations/config_scope_data_model.py` | `FileOpsToolScope` 模型、`resolve_file_ops_scope` 函数 |
| `api/agent/tools/file_operations/storage_backend/juicefs_sdk.py` | JuiceFS 存储后端，W/B 路径校验实现 |
| `api/agent/tools/memory/config_data_model.py` | `MemoryToolScope` 模型、`resolve_memory_scope` 函数 |
| `api/agent/tools/memory/memory_discovery.py` | 记忆索引文件发现（recall/write 共享） |
| `api/agent/tools/memory/recall/tool_init.py` | 召回 Agent 工具构造 |
| `api/agent/tools/memory/write/tool_init.py` | 写入 Agent 工具构造 |
| `api/agent/strategy/main_agent_strategy.py` | 主 agent 策略，记忆系统独立工具构造 |
| `api/agent/tools/bash/config_data_model.py` | `BashToolScope` 模型、`BASH_USER_ID_PATHS` 常量 |

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
            → resolve_scope_value(scope_def, FIELD_PATHS)

      → main_agent_strategy(scope_def=scope_def)
        → resolve_memory_scope(scope_def)
          → build_recall_tool_init_res / build_write_tool_init_res
```

### 工具解析规范

1. 每个工具在对应的 `config_data_model.py` 中声明模块级常量（非类内 ClassVar），命名格式 `<TOOL>_<FIELD>_PATHS`，值为字符串列表，按优先级排列，支持点号分隔的嵌套路径。

2. 使用 `api/agent/session_agent_config/utils.py` 中的 `resolve_scope_value(scope_def, key_paths)` 解析，依次尝试 key_paths 中的每个路径，返回第一个找到的值，全部未找到时抛出 KeyError。

3. 构造器优先级：
   - 优先级 1：`config.tool_scope` 已有（从 overlay 或持久化配置恢复）
   - 优先级 2：从 `scope_def` 通过 `resolve_scope_value` 解析

### 已迁移的工具

| 工具 | ToolScope 模型 | 范式 | Scope Key 常量文件 |
|------|---------------|------|-------------------|
| load_skill | `SkillToolScope` | scope_def + resolve_scope_value | `api/agent/tools/skills/load_skill/config_data_model.py` |
| read_file | `FileOpsToolScope` | scope_def + resolve_scope_value | `api/agent/tools/file_operations/config_scope_data_model.py` |
| edit_file | `FileOpsToolScope` | 同上 | 同上 |
| write_file | `FileOpsToolScope` | 同上 | 同上 |
| list_directory | `FileOpsToolScope` | 同上 | 同上 |
| delete_file | `FileOpsToolScope` | 同上 | 同上 |
| move_file | `FileOpsToolScope` | 同上 | 同上 |
| copy_file | `FileOpsToolScope` | 同上 | 同上 |
| memory_recall | `MemoryToolScope` | 独立工具构造 + resolve_memory_scope | `api/agent/tools/memory/config_data_model.py` |
| memory_write | `MemoryToolScope` | 同上 | 同上 |
| bash | `BashToolScope` | scope_def + resolve_scope_value | `api/agent/tools/bash/config_data_model.py` |

## 待改造的功能

### 项目管理命令（已移除）

`command/project/` 目录已从代码库中移除，不再需要迁移。

### 未迁移的工具

所有工具已完成迁移或确认无需迁移。
