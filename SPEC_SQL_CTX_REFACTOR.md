# SPEC: 数据库操作实用函数 ctx 改造

## 背景

当前项目中所有数据库实用函数（`<module>/sql_stat/<table>/utils.py`）各自独立创建连接并 commit，
无法支持多操作原子事务。改造目标是为每个函数增加可选的 `ctx: SQL_OP_ContextData | None = None` 参数，
通过 `_resolve_conn(ctx)` 辅助函数统一连接获取与提交逻辑。

## 已完成

- [x] `api/sql_utils/utils.py` — 新增 `SQL_OP_ContextData` 数据类 + `_resolve_conn` 辅助函数
- [x] `api/chat/sql_stat/u2a_session/utils.py` — 示例改造（13 函数，已作为参照模板）
- [x] 🅰️ 批次 A：通知模块 4 文件 — 15 函数全部改造完成，语法检查通过
- [x] 🅱️ 批次 B：Agent + 认证模块 3 文件 — 29 函数全部改造完成，语法检查通过
- [x] 🅲 批次 C：Chat 模块 1（2 文件）— 32 函数全部改造完成，语法检查通过。含 wrapper 函数的 ctx 透传。
- [x] 🅳 批次 D：Chat 模块 2（2 文件）— 29 函数全部改造完成，语法检查通过。
- [x] 🅴 批次 E：复杂模块（3 文件）— 57 函数全部改造完成，语法检查通过。
- [x] `api/chat/sql_stat/u2a_session_branch_task/operations.py` — 5 函数，`begin()` → `_resolve_conn(ctx)` 模式，语法检查通过。

## 全部完成：16 文件，~180 函数，全部语法检查通过

---

## 业务层修改 SOP（草案）子代理额外发现并修复了 `u2a_user_short_term_memory/utils.py` 中两处 commit 缩进错误（嵌套 if 块问题）。

## 经验教训（批次 A 复盘）

1. **未使用的 import**：子代理遗漏了移除 `from api.sql_utils import ASYNC_SQL_ENGINE`。已补充为规则 1.5。
2. 其他方面改造质量良好，模式应用正确。

## 改造模式（子代理必须严格遵循）

### 1. 新增 import

```python
from api.sql_utils.utils import SQL_OP_ContextData, _resolve_conn
```

如果该文件已有 `from api.sql_utils.utils import ...` 行，则追加到现有 import 中：
```python
from api.sql_utils.utils import SQL_OP_ContextData, _resolve_conn, now_str, parse_sql_file
```

### 1.5 移除不再使用的 ASYNC_SQL_ENGINE import

改造后，文件中不再直接使用 `ASYNC_SQL_ENGINE.connect()`（该逻辑已封装在 `_resolve_conn` 中），因此需要**删除**原有的：
```python
from api.sql_utils import ASYNC_SQL_ENGINE
```
如果该文件还有其他地方用到 `ASYNC_SQL_ENGINE`（罕见），则保留。

### 2. 函数签名：增加 `ctx` 参数

在所有 `async def xxx(...)` 函数的参数列表末尾添加：
```python
ctx: SQL_OP_ContextData | None = None,
```

如果函数有返回类型注解，ctx 参数放在返回类型注解之前、其他业务参数之后。

### 3. 替换连接创建代码

**原模式：**
```python
async with ASYNC_SQL_ENGINE.connect() as conn:
    # ... SQL 执行 ...
    await conn.commit()  # 写函数有,读函数无
    return ...
```

**新模式（写函数 — 原来有 `await conn.commit()` 的）：**
```python
async with _resolve_conn(ctx) as conn:
    # ... SQL 执行（完全不变）...
    if ctx is None or ctx.auto_commit:
        await conn.commit()
    return ...
```

**新模式（读函数 — 原来无 `await conn.commit()` 的）：**
```python
async with _resolve_conn(ctx) as conn:
    # ... SQL 执行（完全不变）...
    return ...
```

### 4. 关键要点

- **SQL 执行代码不重复**：使用 `async with _resolve_conn(ctx) as conn:` 替换整个 `async with ASYNC_SQL_ENGINE.connect() as conn:` 块，SQL 执行逻辑只写一次
- **写函数提交**：`if ctx is None or ctx.auto_commit: await conn.commit()` — 独立模式或自动提交模式才 commit
- **读函数不提交**：保持原有行为，不添加 commit 调用
- **`conn.commit()` → `ctx.commit()` 不一致问题**：原代码写 `await conn.commit()`，ctx 模式下应使用 `ctx.commit()`。但在 `_resolve_conn` 模式下，conn 在独立模式下是本地连接（可 commit），在 ctx 模式下是 ctx.conn（也可 commit）。为统一，建议统一写成 `await conn.commit()`，因为 `_resolve_conn` 在两种情况下都会提供可 commit 的 conn 对象。**简化写法是统一使用 `await conn.commit()` 即可。**

   实际上，由于 `_resolve_conn` 中，ctx 不为 None 时 `yield ctx.conn`，此时 conn 就是 ctx.conn，`await conn.commit()` 等价于 `await ctx.commit()`。所以无论哪种模式，`await conn.commit()` 都是正确的。

### 5. 禁止的做法

- ❌ 不要在独立模式路径中保留 `await conn.commit()` 而在 ctx 路径中使用 `await ctx.commit()` — 这是重复代码
- ❌ 不要保留原始的 `async with ASYNC_SQL_ENGINE.connect() as conn:` — 全部替换为 `async with _resolve_conn(ctx) as conn:`
- ❌ 不要修改 SQL 执行逻辑、参数绑定、错误处理 — 只改连接获取和提交方式
- ❌ 不要修改 docstring 中已有的参数说明 — 仅追加 `ctx` 参数的文档

## 待改造文件清单（共 14 个文件）

### 批次 A：通知模块（小文件 × 4）— ~426 行, 15 函数

- [ ] `api/system_notification/sql_stat/session_notification/utils.py` (121行, 4funcs)
- [ ] `api/system_notification/sql_stat/system_notification_ack/utils.py` (109行, 4funcs)
- [ ] `api/system_notification/sql_stat/system_notification/utils.py` (84行, 3funcs)
- [ ] `api/system_notification/sql_stat/user_notification/utils.py` (112行, 4funcs)

### 批次 B：Agent + 认证模块（中文件 × 3）— ~856 行, 30 函数

- [ ] `api/agent/sql_stat/u2a_session_agent_config/utils.py` (290行, 10funcs)
- [ ] `api/agent/sql_stat/u2a_session_storage/utils.py` (334行, 11funcs)
- [ ] `api/authentication/sql_stat/utils.py` (232行, 9funcs)

### 批次 C：Chat 模块 1（中文件 × 2）— ~927 行, 32 函数

- [ ] `api/chat/sql_stat/u2a_agent_msg/utils.py` (523行, 16funcs)
- [ ] `api/chat/sql_stat/u2a_agent_short_term_memory/utils.py` (404行, 16funcs)

### 批次 D：Chat 模块 2（中文件 × 2）— ~972 行, 29 函数

- [ ] `api/chat/sql_stat/u2a_session_branch/utils.py` (319行, 11funcs)
- [ ] `api/chat/sql_stat/u2a_user_msg/utils.py` (653行, 18funcs)

### 批次 E：复杂模块（大文件 × 3）— ~1,393 行, 57 函数

- [ ] `api/chat/sql_stat/u2a_session_task/utils.py` (744行, 30funcs)
- [ ] `api/chat/sql_stat/u2a_user_short_term_memory/utils.py` (406行, 14funcs)
- [ ] `api/user_pod_scheduler/sql_stat/utils.py` (243行, 13funcs)

## 特殊文件

### `api/chat/sql_stat/u2a_session_branch_task/operations.py`

该文件使用 `ASYNC_SQL_ENGINE.begin()` 而非 `.connect()`，是不同的事务管理模式。
`begin()` 自动管理事务（退出时 commit 或 rollback）。此文件需要单独设计改造方案，不在本轮批量改造范围内。

## 子代理任务描述

每个子代理将被分配一个批次。子代理应：

1. **读取**目标文件，理解当前结构（解析了哪些 SQL 语句、定义了哪些 dataclass、有哪些 async 函数）
2. **按改造模式**对每个 async 函数进行改造：
   - 添加 `ctx` 参数
   - 替换连接获取方式为 `_resolve_conn(ctx)`
   - 调整 commit 逻辑（写函数）或保持无 commit（读函数）
3. **不改动**：
   - 模块顶部的 SQL 解析逻辑
   - dataclass 定义
   - 函数内部 SQL 执行参数
   - 函数原有 docstring 中的业务参数说明（仅在末尾追加 `ctx` 文档）
4. **运行语法检查**：`python3 -c "import ast; ast.parse(open('<file>').read()); print('OK')"` 验证每个文件

## 验证方式

全部改造完成后，调用现有业务代码的调用方应无需任何修改即可正常工作（因为 `ctx` 默认为 `None`）。
可通过以下命令快速检查调用方是否受影响：

```bash
# 搜索所有调用这些 utils 函数的代码
grep -rn "from.*utils import\|from.*utils import\|\.utils\." api/app/ | grep -v __pycache__
```
