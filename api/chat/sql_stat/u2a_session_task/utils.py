from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import bindparam, text

from api.sql_utils import ASYNC_SQL_ENGINE
from api.sql_utils.utils import parse_sql_file

sql_file_path = Path(__file__).parent / "U2ASessionTask.sql"

sql_statements = parse_sql_file(sql_file_path)

CREATE_TABLE = sql_statements.get_list("CreateSessionTasksTable")
CREATE_SESSION_TASK_TRIGGERS = sql_statements.get_list("CreateSessionTaskTriggers")

INSERT_SESSION_TASK = sql_statements.get_str("InsertSessionTask")

UPDATE_SESSION_TASK_STATUS = sql_statements.get_str("UpdateSessionTaskStatus")
UPDATE_SESSION_TASK_BRANCH_ID = sql_statements.get_str("UpdateSessionTaskBranchId")
UPDATE_SESSION_TASK_CONTEXT_BREAKPOINTS = sql_statements.get_str("UpdateSessionTaskContextBreakpoints")

SESSION_TASK_EXISTS = sql_statements.get_str("SessionTaskExists")
QUERY_SESSION_TASK_BY_ID = sql_statements.get_str("QuerySessionTaskById")
QUERY_SESSION_TASKS_BY_SESSION = sql_statements.get_str("QuerySessionTasksBySession")
QUERY_SESSION_TASK_BY_SESSION_AND_STATUS = sql_statements.get_str("QuerySessionTaskBySessionAndStatus")
QUERY_SESSION_TASKS_BY_USER = sql_statements.get_str("QuerySessionTasksByUser")
GET_NEXT_SEQ_IN_SESSION = sql_statements.get_str("GetNextSeqInSession")
QUERY_SESSION_TASKS_BY_BRANCH_PATH = sql_statements.get_str("QuerySessionTasksByBranchPath")
QUERY_SESSION_TASKS_BY_BRANCH_PATH_UNTIL_BREAKPOINT = sql_statements.get_str("QuerySessionTasksByBranchPathUntilBreakPoint")
QUERY_ANCESTORS_BY_LEAF_TASK_AND_STATUSES = sql_statements.get_str("QueryAncestorsByLeafTaskAndStatuses")
QUERY_CHILD_TASKS_BY_PARENT_ID = sql_statements.get_str("QueryChildTasksByParentId")
QUERY_SESSION_TASK_TREE_PATH = sql_statements.get_str("QuerySessionTaskTreePath")
DELETE_SESSION_TASK = sql_statements.get_str("DeleteSessionTask")
DELETE_SESSION_TASKS_BY_SESSION = sql_statements.get_str("DeleteSessionTasksBySession")

CHECK_SESSION_HAS_TASK_WITH_STATUS = sql_statements.get_str("CheckSessionHasTaskWithStatus")
CHECK_SESSION_HAS_TASK_WITH_STATUSES = sql_statements.get_str("CheckSessionHasTaskWithStatuses")
GET_SESSION_TASK_STATUS_COUNTS = sql_statements.get_str("GetSessionTaskStatusCounts")

UPDATE_SESSION_TASK_STORAGE_SNAPSHOT = sql_statements.get_str("UpdateSessionTaskStorageSnapshot")
QUERY_NEAREST_ANCESTOR_STORAGE_SNAPSHOT = sql_statements.get_str("QueryNearestAncestorStorageSnapshot")
COPY_STORAGE_SNAPSHOT_FROM_NEAREST_ANCESTOR = sql_statements.get_str("CopyStorageSnapshotFromNearestAncestor")

UPDATE_SESSION_TASK_LOGIC_MARK = sql_statements.get_str("UpdateSessionTaskLogicMark")
QUERY_SESSION_TASK_LOGIC_MARK_FIELD = sql_statements.get_str("QuerySessionTaskLogicMarkField")
QUERY_BRANCH_PATH_UNTIL_LOGIC_MARK = sql_statements.get_str("QueryBranchPathUntilLogicMark")
QUERY_NEAREST_ANCESTOR_LOGIC_MARK_FIELD = sql_statements.get_str("QueryNearestAncestorLogicMarkField")


@dataclass
class _U2ASessionTask:
    """U2A会话任务数据模型，该数据模型尽量不应该被其他模块直接存储或长期持有"""
    id: UUID
    session_id: UUID
    user_id: UUID
    status: str
    parent_task_id: UUID | None
    branch_id: UUID | None
    seq_in_session: int
    tree_path: str
    context_breakpoints: list[int]
    storage_snapshot: dict[str, Any] | None
    logic_mark: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


@dataclass
class _U2ASessionTaskCreate:
    """创建U2A会话任务的数据模型"""
    session_id: UUID
    user_id: UUID
    seq_in_session: int
    tree_path: str
    status: str | None = None
    parent_task_id: UUID | None = None
    branch_id: UUID | None = None
    context_breakpoints: list[int] | None = None
    storage_snapshot: dict[str, Any] | None = None
    logic_mark: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


def _row_to_task(row) -> _U2ASessionTask:
    """将数据库行转换为任务模型对象"""
    return _U2ASessionTask(
        id=row.id,
        session_id=row.session_id,
        user_id=row.user_id,
        status=row.status,
        parent_task_id=row.parent_task_id,
        branch_id=row.branch_id,
        seq_in_session=row.seq_in_session,
        tree_path=row.tree_path,
        context_breakpoints=row.context_breakpoints if row.context_breakpoints else [],
        storage_snapshot=dict(row.storage_snapshot) if row.storage_snapshot else None,
        logic_mark=dict(row.logic_mark) if row.logic_mark else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def create_table() -> None:
    """创建U2A会话任务表并设置触发器"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        for stmt in CREATE_TABLE:
            await conn.execute(text(stmt))
        for stmt in CREATE_SESSION_TASK_TRIGGERS:
            await conn.execute(text(stmt))
        await conn.commit()


async def insert_task(task_data: _U2ASessionTaskCreate) -> UUID:
    """插入新U2A会话任务

    Args:
        task_data: 任务创建数据

    Returns:
        新任务的id (数据库生成的UUID)
    """
    if task_data.status is None:
        task_data.status = "pending"
    if task_data.context_breakpoints is None:
        task_data.context_breakpoints = []
    if task_data.storage_snapshot is None:
        task_data.storage_snapshot = None
    if task_data.logic_mark is None:
        task_data.logic_mark = None

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_SESSION_TASK),
            {
                "session_id": task_data.session_id,
                "user_id": task_data.user_id,
                "status": task_data.status,
                "parent_task_id": task_data.parent_task_id,
                "branch_id": task_data.branch_id,
                "seq_in_session": task_data.seq_in_session,
                "tree_path": task_data.tree_path,
                "context_breakpoints": task_data.context_breakpoints,
                "storage_snapshot": task_data.storage_snapshot,
                "logic_mark": task_data.logic_mark,
            },
        )
        await conn.commit()
        return result.scalar()


async def update_task_status(task_id: UUID, new_status: Literal["pending", "processing", "completed", "failed", "cancelled"]) -> bool:
    """更新任务状态

    Args:
        task_id: 任务ID
        new_status: 新状态值

    Returns:
        更新是否成功
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_SESSION_TASK_STATUS),
            {
                "id_value": task_id,
                "status_value": new_status,
            },
        )
        await conn.commit()
        return result.rowcount > 0


async def update_task_branch_id(task_id: UUID, branch_id: UUID | None) -> bool:
    """更新任务的分支ID

    Args:
        task_id: 任务ID
        branch_id: 分支ID，可为None

    Returns:
        更新是否成功
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_SESSION_TASK_BRANCH_ID),
            {"id_value": task_id, "branch_id_value": branch_id},
        )
        await conn.commit()
        return result.rowcount > 0


async def update_task_context_breakpoints(task_id: UUID, breakpoints: list[int]) -> bool:
    """更新任务的上下文断点列表

    Args:
        task_id: 任务ID
        breakpoints: 上下文断点列表

    Returns:
        更新是否成功
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_SESSION_TASK_CONTEXT_BREAKPOINTS),
            {"id_value": task_id, "context_breakpoints_value": breakpoints},
        )
        await conn.commit()
        return result.rowcount > 0


async def task_exists(task_id: UUID) -> bool:
    """检查任务是否存在

    Args:
        task_id: 任务ID

    Returns:
        任务是否存在
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(SESSION_TASK_EXISTS), {"id_value": task_id})
        count = result.scalar()
        return count > 0


async def get_task(task_id: UUID) -> _U2ASessionTask | None:
    """获取任务信息

    Args:
        task_id: 任务ID

    Returns:
        任务信息，如果不存在则返回None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_SESSION_TASK_BY_ID), {"id_value": task_id})
        row = result.first()

        if row is None:
            return None

        return _row_to_task(row)


async def get_tasks_by_session(session_id: UUID) -> list[_U2ASessionTask]:
    """根据会话ID获取所有任务

    Args:
        session_id: 会话ID

    Returns:
        任务列表
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_SESSION_TASKS_BY_SESSION), {"session_id_value": session_id})
        rows = result.fetchall()

        return [_row_to_task(row) for row in rows]


async def get_tasks_by_session_and_status(session_id: UUID, status: str) -> list[_U2ASessionTask]:
    """根据会话ID和状态获取任务

    Args:
        session_id: 会话ID
        status: 状态值

    Returns:
        任务列表
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_SESSION_TASK_BY_SESSION_AND_STATUS),
                                     {"session_id_value": session_id, "status_value": status})
        rows = result.fetchall()
        return [_row_to_task(row) for row in rows]


async def get_tasks_by_user(user_id: UUID) -> list[_U2ASessionTask]:
    """根据用户ID获取所有任务

    Args:
        user_id: 用户ID

    Returns:
        任务列表
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_SESSION_TASKS_BY_USER), {"user_id_value": user_id})
        rows = result.fetchall()

        return [_row_to_task(row) for row in rows]


async def get_next_seq_in_session(session_id: UUID) -> int:
    """获取会话内下一个 seq_in_session 值

    Args:
        session_id: 会话ID

    Returns:
        下一个可用的 seq_in_session 值
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(GET_NEXT_SEQ_IN_SESSION),
            {"session_id_value": session_id},
        )
        return result.scalar()


async def get_task_tree_path(task_id: UUID) -> str | None:
    """获取任务的 tree_path

    Args:
        task_id: 任务ID

    Returns:
        tree_path 字符串，如果任务不存在则返回None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_SESSION_TASK_TREE_PATH),
            {"id_value": task_id},
        )
        row = result.first()

        if row is None:
            return None

        return str(row.tree_path)


async def get_tasks_on_branch_path(leaf_task_id: UUID) -> list[_U2ASessionTask]:
    """沿 parent_task_id 从叶子任务向上遍历到根任务，查询路径上的所有任务

    返回结果按 seq_in_session 升序排序（即时间顺序：root -> leaf）

    Args:
        leaf_task_id: 叶子任务ID

    Returns:
        路径上的所有任务列表，按 seq_in_session 升序
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_SESSION_TASKS_BY_BRANCH_PATH),
            {"leaf_task_id_value": leaf_task_id},
        )
        rows = result.fetchall()

        return [_row_to_task(row) for row in rows]


async def get_ancestors_by_leaf_task_and_statuses(
    leaf_task_id: UUID,
    statuses: list[str],
) -> list[_U2ASessionTask]:
    """沿 branch path 从叶子节点向上查找 status 符合指定值的祖先节点

    返回结果按 seq_in_session 升序排序（即时间顺序：root -> leaf）。

    Args:
        leaf_task_id: 叶子任务ID
        statuses: 要匹配的状态值列表

    Returns:
        路径上 status 符合条件的任务列表，按 seq_in_session 升序
    """
    if not statuses:
        return []

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_ANCESTORS_BY_LEAF_TASK_AND_STATUSES).bindparams(
                bindparam("status_values", expanding=True),
            ),
            {
                "leaf_task_id_value": leaf_task_id,
                "status_values": statuses,
            },
        )
        rows = result.fetchall()

        return [_row_to_task(row) for row in rows]


async def get_tasks_on_branch_path_until_breakpoint(leaf_task_id: UUID) -> list[_U2ASessionTask]:
    """沿 branch path 从叶子任务向上遍历，直到遇到第一个有非空 context_breakpoints 的任务

    包含该 breakpoint 任务。如果路径上没有 breakpoint 任务，则返回完整路径（等同 get_tasks_on_branch_path）。
    返回结果按 seq_in_session 升序排序（即时间顺序：root -> leaf）。

    Args:
        leaf_task_id: 叶子任务ID

    Returns:
        路径上从 breakpoint 到 leaf 的所有任务列表
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_SESSION_TASKS_BY_BRANCH_PATH_UNTIL_BREAKPOINT),
            {"leaf_task_id_value": leaf_task_id},
        )
        rows = result.fetchall()

        return [_row_to_task(row) for row in rows]


async def get_child_tasks(parent_task_id: UUID) -> list[_U2ASessionTask]:
    """查询某个任务的所有直接子任务

    Args:
        parent_task_id: 父任务ID

    Returns:
        子任务列表，按 seq_in_session 排序
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_CHILD_TASKS_BY_PARENT_ID),
            {"parent_task_id_value": parent_task_id},
        )
        rows = result.fetchall()

        return [_row_to_task(row) for row in rows]


async def delete_task(task_id: UUID) -> bool:
    """删除任务

    Args:
        task_id: 任务ID

    Returns:
        删除是否成功（如果任务不存在，返回False）
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(DELETE_SESSION_TASK), {"id_value": task_id})
        await conn.commit()
        return result.rowcount > 0

async def delete_tasks_by_session(session_id: UUID) -> bool:
    """删除指定会话的所有任务

    Args:
        session_id: 会话ID

    Returns:
        删除是否成功
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(DELETE_SESSION_TASKS_BY_SESSION), {"session_id_value": session_id})
        await conn.commit()
        return result.rowcount > 0


async def check_session_has_task_with_status(session_id: UUID, status: str) -> bool:
    """检查指定会话是否有特定状态的任务

    Args:
        session_id: 会话ID
        status: 任务状态 ('pending', 'processing', 'completed', 'failed', 'cancelled')

    Returns:
        是否存在该状态的任务
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(CHECK_SESSION_HAS_TASK_WITH_STATUS),
            {"session_id_value": session_id, "status_value": status},
        )
        count = result.scalar()
        return count > 0


async def check_session_has_task_with_statuses(session_id: UUID, statuses: list[str]) -> bool:
    """检查指定会话是否有任何指定状态的任务

    Args:
        session_id: 会话ID
        statuses: 任务状态列表

    Returns:
        是否存在任何指定状态的任务
    """
    if not statuses:
        return False

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(CHECK_SESSION_HAS_TASK_WITH_STATUSES).bindparams(
                bindparam("status_values", expanding=True),
            ),
            {
                "session_id_value": session_id,
                "status_values": statuses,
            },
        )
        count = result.scalar()
        return count > 0


async def get_session_task_status_counts(session_id: UUID) -> dict[str, int]:
    """获取指定会话的任务状态计数

    Args:
        session_id: 会话ID

    Returns:
        按状态分组的任务计数字典
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(GET_SESSION_TASK_STATUS_COUNTS), {"session_id_value": session_id})
        rows = result.fetchall()

        status_counts = {}
        for row in rows:
            status_counts[row.status] = row.count

        return status_counts


async def update_task_storage_snapshot(task_id: UUID, storage_snapshot: dict[str, Any] | None) -> bool:
    """更新任务的 storage_snapshot 字段

    Args:
        task_id: 任务ID
        storage_snapshot: 要存储的 JSONB 数据，None 表示清除

    Returns:
        更新是否成功
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_SESSION_TASK_STORAGE_SNAPSHOT),
            {"id_value": task_id, "storage_snapshot_value": storage_snapshot},
        )
        await conn.commit()
        return result.rowcount > 0


async def get_nearest_ancestor_storage_snapshot(task_id: UUID) -> dict[str, Any] | None:
    """查找给定任务节点最近的 storage_snapshot 非空的祖先节点，返回其 storage_snapshot

    沿 tree_path 向上查找，返回 seq_in_session 最大的（离 leaf 最近）
    且 storage_snapshot IS NOT NULL 的祖先节点的值。
    包含自身（如果自身 storage_snapshot 非空，则返回自身的值）。

    Args:
        task_id: 任务ID

    Returns:
        最近祖先的 storage_snapshot，如果没有则返回 None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_NEAREST_ANCESTOR_STORAGE_SNAPSHOT),
            {"task_id_value": task_id},
        )
        row = result.first()
        if row is None:
            return None
        return dict(row.storage_snapshot)


async def copy_storage_snapshot_from_nearest_ancestor(task_id: UUID) -> bool:
    """从给定任务节点最近的 storage_snapshot 非空的祖先节点复制到自身

    沿 tree_path 向上查找最近的 storage_snapshot 非空的祖先，将其值复制到当前任务。
    包含自身（如果自身 storage_snapshot 非空，相当于无操作）。

    Args:
        task_id: 任务ID

    Returns:
        是否实际发生了复制（如果不存在有 storage_snapshot 的祖先则返回 False）
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(COPY_STORAGE_SNAPSHOT_FROM_NEAREST_ANCESTOR),
            {"task_id_value": task_id},
        )
        await conn.commit()
        return result.rowcount > 0


async def update_task_logic_mark(task_id: UUID, logic_mark: dict[str, Any] | None) -> bool:
    """更新任务的 logic_mark 字段

    Args:
        task_id: 任务ID
        logic_mark: 要存储的 JSONB 数据，None 表示清除

    Returns:
        更新是否成功
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_SESSION_TASK_LOGIC_MARK),
            {"id_value": task_id, "logic_mark_value": logic_mark},
        )
        await conn.commit()
        return result.rowcount > 0


async def get_task_logic_mark_field(task_id: UUID, field_key: str) -> Any | None:
    """获取任务 logic_mark 中指定字段的值

    Args:
        task_id: 任务ID
        field_key: JSONB 中的字段名

    Returns:
        字段值（JSONB 类型），如果任务不存在或字段不存在则返回 None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_SESSION_TASK_LOGIC_MARK_FIELD),
            {"id_value": task_id, "field_key": field_key},
        )
        row = result.first()
        if row is None:
            return None
        return row[0]


async def get_tasks_on_branch_path_until_logic_mark(
    leaf_task_id: UUID,
    mark_key: str,
    fallback_to_full_path: bool = True,
) -> list[_U2ASessionTask]:
    """沿 branch path 从叶子任务向上遍历，直到遇到第一个存在指定 logic_mark 字段的祖先任务

    包含该标记任务自身。搜索范围包含叶子节点自身（如果自身有该标记，则只返回自身）。
    返回结果按 seq_in_session 升序排序（即时间顺序：root -> leaf）。

    Args:
        leaf_task_id: 叶子任务ID
        mark_key: 要查找的 logic_mark 字段名（仅检查字段是否存在，不关心内容）
        fallback_to_full_path: 如果路径上没有任何任务有该标记字段，
            True 则返回完整路径，False 则返回空列表

    Returns:
        路径上从标记任务到叶子的所有任务列表
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_BRANCH_PATH_UNTIL_LOGIC_MARK),
            {
                "leaf_task_id_value": leaf_task_id,
                "mark_key": mark_key,
                "fallback_to_full_path": fallback_to_full_path,
            },
        )
        rows = result.fetchall()
        return [_row_to_task(row) for row in rows]


async def get_nearest_ancestor_logic_mark_field(task_id: UUID, mark_key: str) -> Any | None:
    """查找给定任务节点最近的拥有指定 logic_mark 字段的祖先，返回该字段的内容

    沿 tree_path 向上查找，返回 seq_in_session 最大的（离 leaf 最近）
    且 logic_mark 中包含 mark_key 字段的祖先的该字段值。
    搜索范围包含自身。

    Args:
        task_id: 任务ID
        mark_key: 要查找的 logic_mark 字段名

    Returns:
        最近祖先的 mark_key 字段内容，如果找不到则返回 None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_NEAREST_ANCESTOR_LOGIC_MARK_FIELD),
            {"task_id_value": task_id, "mark_key": mark_key},
        )
        row = result.first()
        if row is None:
            return None
        return row[0]
