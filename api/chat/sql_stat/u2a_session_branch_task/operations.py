from typing import Literal
from uuid import UUID
from uuid6 import uuid7

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB

from api.agent.logic_mark_def import TO_REMINDER_BRANCH_CHANGED_MARK_NAME, TO_REMINDER_TOOL_ENABLE_STATUS_MARK_NAME
from api.sql_utils.utils import SQL_OP_ContextData, _resolve_conn
from api.chat.sql_stat.u2a_session_branch.utils import (
    INSERT_SESSION_BRANCH,
    QUERY_SESSION_BRANCH_BY_ID,
    QUERY_SESSION_BRANCH_BY_SESSION_AND_NAME,
    UPDATE_SESSION_BRANCH_LEAF_TASK,
)
from api.chat.sql_stat.u2a_session_task.utils import (
    COPY_STORAGE_SNAPSHOT_FROM_NEAREST_ANCESTOR,
    DELETE_SESSION_TASK,
    INSERT_SESSION_TASK,
    GET_NEXT_SEQ_IN_SESSION,
    QUERY_SESSION_TASK_BY_ID,
    QUERY_SESSION_TASK_TREE_PATH,
    UPDATE_SESSION_TASK_BRANCH_ID,
    UPDATE_SESSION_TASK_LOGIC_MARK_WITHIN_MERGING_OBJECT,
    UPDATE_SESSION_TASK_STORAGE_SNAPSHOT,
)

# 锁定 session 行，防止并发事务产生相同 seq_in_session
_LOCK_SESSION = "SELECT id FROM u2a_sessions WHERE id = :session_id FOR UPDATE"


def construct_branch_name(branch_name: str):
    """ 生成符合 redis key 规则的分支名称
    """

    uuid = uuid7()
    return f"{branch_name}:{uuid!s}"


def strip_branch_name_uuid(raw_name: str) -> str:
    """去除 construct_branch_name 追加的 ':uuid' 后缀。

    是 construct_branch_name 的逻辑逆操作，用于前端展示。

    Examples:
        'main'                          -> 'main'
        '__sub_agent_coder:0194abcd-...' -> '__sub_agent_coder'
    """
    last_colon = raw_name.rfind(':')
    if last_colon >= 0:
        return raw_name[:last_colon]
    return raw_name


def is_hidden_branch_name(raw_name: str) -> bool:
    """以 '__' 开头的分支为隐藏分支（子代理创建）。"""
    return raw_name.startswith('__')

async def append_task_to_branch(
    branch_id: UUID,
    user_id: UUID,
    *,
    status: str = "pending",
    ctx: SQL_OP_ContextData | None = None,
) -> UUID:
    """在现有分支末尾追加新任务

    事务内完成：查询 branch/task → 计算 seq/path → 插入 task → 更新指针

    Args:
        branch_id: 分支ID
        user_id: 用户ID
        status: 任务状态，默认 "pending"
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        新任务的ID

    Raises:
        ValueError: branch 或其 leaf_task 不存在
    """
    async with _resolve_conn(ctx) as conn:
        # 1. 查询 branch → leaf_task_id, session_id
        result = await conn.execute(
            text(QUERY_SESSION_BRANCH_BY_ID),
            {"id_value": branch_id},
        )
        branch = result.first()
        if branch is None:
            raise ValueError(f"Branch {branch_id} not found")

        leaf_task_id = branch.leaf_task_id
        session_id = branch.session_id

        # 2. 锁定 session 行，防止并发产生相同 seq
        await conn.execute(text(_LOCK_SESSION), {"session_id": session_id})

        # 3. 查询 leaf task 的 tree_path
        result = await conn.execute(
            text(QUERY_SESSION_TASK_TREE_PATH),
            {"id_value": leaf_task_id},
        )
        path_row = result.first()
        if path_row is None:
            raise ValueError(f"Leaf task {leaf_task_id} not found")
        leaf_tree_path = str(path_row.tree_path)

        # 4. 获取 next seq_in_session
        result = await conn.execute(
            text(GET_NEXT_SEQ_IN_SESSION),
            {"session_id_value": session_id},
        )
        new_seq = result.scalar()

        # 5. 计算 new_tree_path
        new_tree_path = f"{leaf_tree_path}.t{new_seq}"

        # 6. INSERT new task
        result = await conn.execute(
            text(INSERT_SESSION_TASK),
            {
                "session_id": session_id,
                "user_id": user_id,
                "status": status,
                "parent_task_id": leaf_task_id,
                "branch_id": branch_id,
                "seq_in_session": new_seq,
                "tree_path": new_tree_path,
                "context_breakpoints": [],
                "storage_snapshot": None,
                "logic_mark": None,
            },
        )
        new_task_id = result.scalar()

        # 6.5 复制最近祖先的 storage_snapshot
        _r = await conn.execute(
            text(COPY_STORAGE_SNAPSHOT_FROM_NEAREST_ANCESTOR),
            {"task_id_value": new_task_id},
        )
        if _r.rowcount == 0:
            await conn.execute(
                text(UPDATE_SESSION_TASK_STORAGE_SNAPSHOT).bindparams(
                    bindparam("storage_snapshot_value", type_=JSONB),
                ),
                {"id_value": new_task_id, "storage_snapshot_value": {}},
            )

        # 7. 原 leaf 不再是叶子 → branch_id = NULL
        await conn.execute(
            text(UPDATE_SESSION_TASK_BRANCH_ID),
            {"id_value": leaf_task_id, "branch_id_value": None},
        )

        # 8. 更新 branch 指向新 task
        await conn.execute(
            text(UPDATE_SESSION_BRANCH_LEAF_TASK),
            {"id_value": branch_id, "leaf_task_id_value": new_task_id},
        )

        if ctx is None or ctx.auto_commit:
            await conn.commit()
        return new_task_id


async def fork_branch(
    session_id: UUID,
    name: str,
    created_by: Literal["user", "agent", "system"],
    parent_task_id: UUID,
    user_id: UUID,
    *,
    status: str = "pending",
    ctx: SQL_OP_ContextData | None = None,
) -> tuple[UUID, UUID]:
    """从历史 task 分叉出新分支（含新 task）

    事务内完成：查询 parent → 计算 seq/path → 插入 task → 插入 branch → 回填 branch_id

    Args:
        session_id: 会话ID
        name: 新分支名称（session 内唯一）
        created_by: 创建者 ('user' | 'agent' | 'system')
        parent_task_id: 分叉点的 task ID
        user_id: 用户ID
        status: 任务状态，默认 "pending"
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        (branch_id, task_id)

    Raises:
        ValueError: parent_task 不存在
    """
    async with _resolve_conn(ctx) as conn:
        # 1. 锁定 session 行
        await conn.execute(text(_LOCK_SESSION), {"session_id": session_id})

        # 2. 查询 parent task 的 tree_path
        result = await conn.execute(
            text(QUERY_SESSION_TASK_TREE_PATH),
            {"id_value": parent_task_id},
        )
        path_row = result.first()
        if path_row is None:
            raise ValueError(f"Parent task {parent_task_id} not found")
        parent_tree_path = str(path_row.tree_path)

        # 3. 获取 next seq_in_session
        result = await conn.execute(
            text(GET_NEXT_SEQ_IN_SESSION),
            {"session_id_value": session_id},
        )
        new_seq = result.scalar()

        # 4. 计算 new_tree_path
        new_tree_path = f"{parent_tree_path}.t{new_seq}"

        # 5. INSERT task（branch_id 暂为 NULL）
        result = await conn.execute(
            text(INSERT_SESSION_TASK),
            {
                "session_id": session_id,
                "user_id": user_id,
                "status": status,
                "parent_task_id": parent_task_id,
                "branch_id": None,
                "seq_in_session": new_seq,
                "tree_path": new_tree_path,
                "context_breakpoints": [],
                "storage_snapshot": None,
                "logic_mark": None,
            },
        )
        new_task_id = result.scalar()

        # 5.5 复制最近祖先的 storage_snapshot
        _r = await conn.execute(
            text(COPY_STORAGE_SNAPSHOT_FROM_NEAREST_ANCESTOR),
            {"task_id_value": new_task_id},
        )
        if _r.rowcount == 0:
            await conn.execute(
                text(UPDATE_SESSION_TASK_STORAGE_SNAPSHOT).bindparams(
                    bindparam("storage_snapshot_value", type_=JSONB),
                ),
                {"id_value": new_task_id, "storage_snapshot_value": {}},
            )

        # 6. INSERT branch（leaf_task_id = new_task_id）
        result = await conn.execute(
            text(INSERT_SESSION_BRANCH),
            {
                "session_id": session_id,
                "name": name,
                "created_by": created_by,
                "leaf_task_id": new_task_id,
            },
        )
        new_branch_id = result.scalar()

        # 7. 回填 task.branch_id
        await conn.execute(
            text(UPDATE_SESSION_TASK_BRANCH_ID),
            {"id_value": new_task_id, "branch_id_value": new_branch_id},
        )

        if ctx is None or ctx.auto_commit:
            await conn.commit()
        return new_branch_id, new_task_id


async def create_root_task_with_branch(
    session_id: UUID,
    user_id: UUID,
    name: str,
    created_by: Literal["user", "agent", "system"],
    *,
    status: str = "pending",
    ctx: SQL_OP_ContextData | None = None,
) -> tuple[UUID, UUID]:
    """创建会话的第一个 task 和默认分支

    事务内完成：插入 root task → 插入 branch → 回填 branch_id

    Args:
        session_id: 会话ID
        user_id: 用户ID
        name: 分支名称
        created_by: 创建者
        status: 任务状态，默认 "pending"
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        (branch_id, task_id)
    """
    async with _resolve_conn(ctx) as conn:
        # 1. 锁定 session 行
        await conn.execute(text(_LOCK_SESSION), {"session_id": session_id})

        # 2. 获取 next seq（首个应为 0）
        result = await conn.execute(
            text(GET_NEXT_SEQ_IN_SESSION),
            {"session_id_value": session_id},
        )
        new_seq = result.scalar()

        # 3. root task path
        new_tree_path = f"t{new_seq}"

        # 4. INSERT root task
        result = await conn.execute(
            text(INSERT_SESSION_TASK),
            {
                "session_id": session_id,
                "user_id": user_id,
                "status": status,
                "parent_task_id": None,
                "branch_id": None,
                "seq_in_session": new_seq,
                "tree_path": new_tree_path,
                "context_breakpoints": [],
                "storage_snapshot": None,
                "logic_mark": None,
            },
        )
        new_task_id = result.scalar()

        # 4.1 root task 无祖先，直接设storage_snapshot为空 dict
        await conn.execute(
            text(UPDATE_SESSION_TASK_STORAGE_SNAPSHOT).bindparams(
                bindparam("storage_snapshot_value", type_=JSONB),
            ),
            {"id_value": new_task_id, "storage_snapshot_value": {}},
        )

        # 4.2 设置 logic_mark
        await conn.execute(
            text(UPDATE_SESSION_TASK_LOGIC_MARK_WITHIN_MERGING_OBJECT).bindparams(
                bindparam("logic_mark_value", type_=JSONB),
            ),
            {
                "id_value": new_task_id,
                "logic_mark_value": {
                    TO_REMINDER_TOOL_ENABLE_STATUS_MARK_NAME: True,
                    TO_REMINDER_BRANCH_CHANGED_MARK_NAME: True,
                },
            },
        )
        
        # 5. INSERT branch
        result = await conn.execute(
            text(INSERT_SESSION_BRANCH),
            {
                "session_id": session_id,
                "name": name,
                "created_by": created_by,
                "leaf_task_id": new_task_id,
            },
        )
        new_branch_id = result.scalar()

        # 6. 回填 task.branch_id
        await conn.execute(
            text(UPDATE_SESSION_TASK_BRANCH_ID),
            {"id_value": new_task_id, "branch_id_value": new_branch_id},
        )

        if ctx is None or ctx.auto_commit:
            await conn.commit()
        return new_branch_id, new_task_id


async def delete_branch_leaf_task(
    branch_id: UUID,
    ctx: SQL_OP_ContextData | None = None,
) -> bool:
    """删除分支的叶子任务

    - 有父节点：branch 指针回退到父节点
    - 无父节点（root）：同时删除 branch

    Args:
        branch_id: 分支ID

    Returns:
        是否成功（branch 不存在或 leaf_task 不存在时返回 False）
    """
    async with _resolve_conn(ctx) as conn:
        # 1. 查询 branch
        result = await conn.execute(
            text(QUERY_SESSION_BRANCH_BY_ID),
            {"id_value": branch_id},
        )
        branch = result.first()
        if branch is None:
            if ctx is None or ctx.auto_commit:
                await conn.commit()
            return False

        leaf_task_id = branch.leaf_task_id

        # 2. 查询 leaf task → parent_task_id
        result = await conn.execute(
            text(QUERY_SESSION_TASK_BY_ID),
            {"id_value": leaf_task_id},
        )
        leaf_task = result.first()
        if leaf_task is None:
            if ctx is None or ctx.auto_commit:
                await conn.commit()
            return False

        parent_task_id = leaf_task.parent_task_id

        # 3. 有 parent 时，先更新 branch 指针到 parent（必须在 DELETE 之前，否则 CASCADE 会删掉 branch）
        if parent_task_id is not None:
            await conn.execute(
                text(UPDATE_SESSION_BRANCH_LEAF_TASK),
                {"id_value": branch_id, "leaf_task_id_value": parent_task_id},
            )
            await conn.execute(
                text(UPDATE_SESSION_TASK_BRANCH_ID),
                {"id_value": parent_task_id, "branch_id_value": branch_id},
            )

        # 4. DELETE leaf task（CASCADE 自动删除子 task；无 parent 时 CASCADE 同时删除 branch）
        await conn.execute(
            text(DELETE_SESSION_TASK),
            {"id_value": leaf_task_id},
        )

        if ctx is None or ctx.auto_commit:
            await conn.commit()
        return True


async def get_or_create_pending_task(
    session_id: UUID,
    user_id: UUID,
    branch_name: str = "main",
    ctx: SQL_OP_ContextData | None = None,
) -> tuple[UUID, bool]:
    """原子性地获取或创建指定分支上的 pending 任务

    在单个事务内完成：
    1. 锁定 session 行
    2. 查找 branch (session_id + branch_name)
    3. 如果 branch 不存在：创建 root task + branch
    4. 如果 branch 存在：检查 leaf task 状态
       - pending → 复用
       - 其他 → 追加新 task

    Args:
        session_id: 会话ID
        user_id: 用户ID
        branch_name: 分支名称，默认 "main"
        ctx: 可选的数据库操作上下文，用于共享连接和事务控制

    Returns:
        (task_id, is_new_task)
    """
    async with _resolve_conn(ctx) as conn:
        # 1. 锁定 session 行
        await conn.execute(text(_LOCK_SESSION), {"session_id": session_id})

        # 2. 查找 branch
        result = await conn.execute(
            text(QUERY_SESSION_BRANCH_BY_SESSION_AND_NAME),
            {"session_id_value": session_id, "name_value": branch_name},
        )
        branch = result.first()

        if branch is None:
            raise ValueError("branch not found")

        # 4. branch 存在 → 检查 leaf task
        leaf_task_id = branch.leaf_task_id
        branch_id = branch.id

        result = await conn.execute(
            text(QUERY_SESSION_TASK_BY_ID),
            {"id_value": leaf_task_id},
        )
        leaf_task = result.first()

        if leaf_task is not None and leaf_task.status == "pending":
            # leaf task 已经 pending → 复用
            if ctx is None or ctx.auto_commit:
                await conn.commit()
            return leaf_task.id, False

        # leaf task 非 pending → 追加新 pending task
        result = await conn.execute(
            text(QUERY_SESSION_TASK_TREE_PATH),
            {"id_value": leaf_task_id},
        )
        path_row = result.first()
        leaf_tree_path = str(path_row.tree_path)

        result = await conn.execute(
            text(GET_NEXT_SEQ_IN_SESSION),
            {"session_id_value": session_id},
        )
        new_seq = result.scalar()
        new_tree_path = f"{leaf_tree_path}.t{new_seq}"

        result = await conn.execute(
            text(INSERT_SESSION_TASK),
            {
                "session_id": session_id,
                "user_id": user_id,
                "status": "pending",
                "parent_task_id": leaf_task_id,
                "branch_id": branch_id,
                "seq_in_session": new_seq,
                "tree_path": new_tree_path,
                "context_breakpoints": [],
                "storage_snapshot": None,
                "logic_mark": None,
            },
        )
        new_task_id = result.scalar()

        # 复制最近祖先的 storage_snapshot
        _r = await conn.execute(
            text(COPY_STORAGE_SNAPSHOT_FROM_NEAREST_ANCESTOR),
            {"task_id_value": new_task_id},
        )
        if _r.rowcount == 0:
            await conn.execute(
                text(UPDATE_SESSION_TASK_STORAGE_SNAPSHOT).bindparams(
                    bindparam("storage_snapshot_value", type_=JSONB),
                ),
                {"id_value": new_task_id, "storage_snapshot_value": {}},
            )

        # 原 leaf 不再是叶子
        await conn.execute(
            text(UPDATE_SESSION_TASK_BRANCH_ID),
            {"id_value": leaf_task_id, "branch_id_value": None},
        )

        # 更新 branch 指向新 task
        await conn.execute(
            text(UPDATE_SESSION_BRANCH_LEAF_TASK),
            {"id_value": branch_id, "leaf_task_id_value": new_task_id},
        )

        if ctx is None or ctx.auto_commit:
            await conn.commit()
        return new_task_id, True
