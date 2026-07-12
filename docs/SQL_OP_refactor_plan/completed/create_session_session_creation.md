# 候选：create_session 会话创建原子化

**状态**: 已完成
**发现日期**: 2026-07-12
**优先级建议**: P0

## 涉及文件

- `api/app/chat/create_session.py` — 业务入口 `create_session()`
- `api/chat/sql_stat/u2a_session/utils.py` — `insert_session()`
- `api/agent/sql_stat/u2a_session_agent_config/utils.py` — `insert_session_config()`
- `api/chat/sql_stat/u2a_session_branch_task/operations.py` — `create_root_task_with_branch()`

## 当前调用链

```
create_session()
  ├─ insert_session(session_data)                                    ← 独立事务 #1 (写, auto-commit)
  ├─ insert_session_config(config_data)                              ← 独立事务 #2 (写, auto-commit)
  └─ create_root_task_with_branch(session_id, user_id, "main")      ← 独立事务 #3 (写, auto-commit)
                                                                      内部含多个子步骤:
                                                                      INSERT task → UPDATE storage_snapshot
                                                                      → SET logic_mark → INSERT branch
                                                                      → UPDATE task.branch_id
```

三个写操作分别 commit，中间任何一步失败都不会回滚已提交的前序步骤。

## 当前风险

| 失败点 | 已持久化的数据 | 后果 |
|--------|---------------|------|
| `insert_session_config` 失败 | u2a_sessions 行已插入 | **孤儿 session**：无 config、无 task/branch，无法正常使用，前端可能看到空会话 |
| `create_root_task_with_branch` 失败 | u2a_sessions + u2a_session_agent_config 均已插入 | **半残 session**：有 session + config，但无 root task 和 branch，process_pending_messages 会因为找不到 leaf_task 而报错 |

这个路径在 `create_session` 中被频繁调用（新建会话的入口），一旦发生异常（DB 瞬时故障、config 验证失败等），会在生产环境产生难以清理的孤儿数据。

## 改造方案

- **ctx 创建位置**：`create_session()` 函数体内，`insert_session` 调用之前
- **ctx 作用域**：覆盖 `insert_session` → `insert_session_config` → `create_root_task_with_branch` 全部三个写操作
- **是否需要跨模块透传**：是。三个函数来自三个不同模块的 utils 文件（`api/chat/sql_stat/u2a_session`、`api/agent/sql_stat/u2a_session_agent_config`、`api/chat/sql_stat/u2a_session_branch_task`），均已完成 ctx 改造，透传无阻碍
- **异常处理调整**：当前 `except Exception as e: raise HTTPException(500, ...)` —— exception handler 不做额外调整，ctx 的 `__aexit__` 在异常时会自动 rollback。但需注意：`create_root_task_with_branch` 内部使用了 `SELECT ... FOR UPDATE` 行锁，在共享 ctx 模式下，该锁会在 `insert_session` INSERT 之后获取，逻辑上正确（先插入行，再锁定它）

## 伪代码

```python
# 改造前
@router.post("/sessions/create", response_model=CreateSessionResponse)
async def create_session(
    request: CreateSessionRequest,
    current_user: Annotated[_User, Depends(get_current_active_user)],
) -> CreateSessionResponse:
    try:
        # ... 复用已有空会话的逻辑（纯读，不涉及 ctx）...

        # 创建新会话 — 三步独立事务
        session_data = _U2ASessionCreate(
            user_id=current_user.id,
            title=request.title,
            created_by="user",
        )
        new_session_id = await insert_session(session_data)          # commit #1

        config = DEFAULT_MAIN_AGENT_SESSION_CONFIG.model_copy(deep=True)
        config.scope_def = _build_default_scope_def(str(current_user.id))
        await insert_session_config(_U2ASessionAgentConfigCreate(   # commit #2
            session_id=new_session_id,
            config=config.model_dump(mode="json"),
        ))

        await create_root_task_with_branch(                          # commit #3
            new_session_id, current_user.id, "main", "user",
        )

        return CreateSessionResponse(...)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建会话失败: {e!s}") from e


# 改造后
@router.post("/sessions/create", response_model=CreateSessionResponse)
async def create_session(
    request: CreateSessionRequest,
    current_user: Annotated[_User, Depends(get_current_active_user)],
) -> CreateSessionResponse:
    try:
        # ... 复用已有空会话的逻辑（纯读，不涉及 ctx）...

        # 创建新会话 — 三步合并在一个事务内
        from api.sql_utils.utils import SQL_OP_ContextData

        session_data = _U2ASessionCreate(
            user_id=current_user.id,
            title=request.title,
            created_by="user",
        )

        ctx = SQL_OP_ContextData(
            description="create_session: session + config + root_task_and_branch",
            auto_commit=False,
        )
        async with ctx:
            new_session_id = await insert_session(session_data, ctx=ctx)

            config = DEFAULT_MAIN_AGENT_SESSION_CONFIG.model_copy(deep=True)
            config.scope_def = _build_default_scope_def(str(current_user.id))
            await insert_session_config(
                _U2ASessionAgentConfigCreate(
                    session_id=new_session_id,
                    config=config.model_dump(mode="json"),
                ),
                ctx=ctx,
            )

            await create_root_task_with_branch(
                new_session_id, current_user.id, "main", "user",
                ctx=ctx,
            )

            await ctx.commit()

        return CreateSessionResponse(
            session_uuid=new_session_id,
            created_new_session=True,
            message="会话创建成功",
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建会话失败: {e!s}") from e
```

## 注意事项

1. **`SELECT ... FOR UPDATE` 锁顺序**：`create_root_task_with_branch` 内部执行 `SELECT id FROM u2a_sessions WHERE id = :session_id FOR UPDATE` 时会获取行锁。在改造前这是独立事务中的锁，改造后由于 `insert_session` 已在同一事务中 INSERT 了该行，`FOR UPDATE` 会对已存在的行加锁，行为正确。
2. **并发考虑**：`create_session` 入口有"复用空会话"的逻辑（查询最新 `created_by="user"` 的会话，若无消息则直接返回）。这部分是纯读操作，不参与写事务，无需 ctx 包裹。但若在"复用检查"和"新会话创建"之间有并发请求，仍可能产生两个空会话——这是现有逻辑的设计，ctx 改造不改变此行为。
3. **异常处理**：`SQL_OP_ContextData.__aexit__` 在异常时会自动 `rollback()`，无需额外编写 rollback 代码。当前 `except` 块只需将异常包装为 HTTPException 即可。
4. **无回滚副作用**：三个操作都是纯 DB INSERT（无外部 API 调用、无 Redis 写入、无文件操作），因此 rollback 无副作用。
