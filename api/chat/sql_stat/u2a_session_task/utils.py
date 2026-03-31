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

CREATE_TABLE = sql_statements["CreateSessionTasksTable"]
CREATE_SESSION_TASK_TRIGGERS = sql_statements["CreateSessionTaskTriggers"]

INSERT_SESSION_TASK = sql_statements["InsertSessionTask"]

UPDATE_SESSION_TASK1 = sql_statements["UpdateSessionTask1"]
UPDATE_SESSION_TASK2 = sql_statements["UpdateSessionTask2"]
UPDATE_SESSION_TASK3 = sql_statements["UpdateSessionTask3"]
UPDATE_SESSION_TASK_STATUS = sql_statements["UpdateSessionTaskStatus"]
UPDATE_SESSION_TASK_BRANCH_ID = sql_statements["UpdateSessionTaskBranchId"]
UPDATE_SESSION_TASK_CONTEXT_BREAKPOINTS = sql_statements["UpdateSessionTaskContextBreakpoints"]

SESSION_TASK_EXISTS = sql_statements["SessionTaskExists"]
QUERY_SESSION_TASK_BY_ID = sql_statements["QuerySessionTaskById"]
QUERY_SESSION_TASKS_BY_SESSION = sql_statements["QuerySessionTasksBySession"]
QUERY_SESSION_TASK_BY_SESSION_AND_STATUS = sql_statements["QuerySessionTaskBySessionAndStatus"]
QUERY_SESSION_TASKS_BY_USER = sql_statements["QuerySessionTasksByUser"]
GET_NEXT_SEQ_IN_SESSION = sql_statements["GetNextSeqInSession"]
QUERY_SESSION_TASKS_BY_BRANCH_PATH = sql_statements["QuerySessionTasksByBranchPath"]
QUERY_SESSION_TASKS_BY_BRANCH_PATH_UNTIL_BREAKPOINT = sql_statements["QuerySessionTasksByBranchPathUntilBreakPoint"]
QUERY_CHILD_TASKS_BY_PARENT_ID = sql_statements["QueryChildTasksByParentId"]
QUERY_SESSION_TASK_TREE_PATH = sql_statements["QuerySessionTaskTreePath"]
QUERY_SESSION_TASK_FIELD1 = sql_statements["QuerySessionTaskField1"]
QUERY_SESSION_TASK_FIELD2 = sql_statements["QuerySessionTaskField2"]
QUERY_SESSION_TASK_FIELD3 = sql_statements["QuerySessionTaskField3"]
QUERY_SESSION_TASK_FIELD4 = sql_statements["QuerySessionTaskField4"]
DELETE_SESSION_TASK = sql_statements["DeleteSessionTask"]
DELETE_SESSION_TASKS_BY_SESSION = sql_statements["DeleteSessionTasksBySession"]

CHECK_SESSION_HAS_TASK_WITH_STATUS = sql_statements["CheckSessionHasTaskWithStatus"]
CHECK_SESSION_HAS_TASK_WITH_STATUSES = sql_statements["CheckSessionHasTaskWithStatuses"]
GET_SESSION_TASK_STATUS_COUNTS = sql_statements["GetSessionTaskStatusCounts"]

# 所有可查询/更新的字段名
_TASK_FIELD_NAMES = Literal[
    "id", "session_id", "user_id", "status",
    "parent_task_id", "branch_id", "seq_in_session", "tree_path",
    "context_breakpoints",
    "created_at", "updated_at",
]


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
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class _U2ASessionTaskUpdate:
    """更新U2A会话任务的数据模型"""
    task_id: UUID
    fields: dict[
        _TASK_FIELD_NAMES,
        str | bool | int | list[int] | None,
    ]


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
            },
        )
        await conn.commit()
        return result.scalar()


async def update_task_fields(update_data: _U2ASessionTaskUpdate) -> bool:
    """更新任务字段

    Args:
        update_data: 任务更新数据

    Returns:
        更新是否成功
    """
    field_count = len(update_data.fields)

    if field_count == 0:
        return False
    elif field_count == 1:
        sql = UPDATE_SESSION_TASK1
    elif field_count == 2:
        sql = UPDATE_SESSION_TASK2
    elif field_count == 3:
        sql = UPDATE_SESSION_TASK3
    else:
        raise ValueError(f"Unsupported field count: {field_count}")

    params: dict[str, Any] = {"id_value": update_data.task_id}
    for i, (field, value) in enumerate(update_data.fields.items(), 1):
        sql = sql.replace(f":field_name_{i}", field)  # type: ignore[union-attr]
        params[f"field_value_{i}"] = value

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(sql), params)  # type: ignore[arg-type]
        await conn.commit()
        return result.rowcount > 0


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


async def get_task_field(
    task_id: UUID,
    field_name: _TASK_FIELD_NAMES,
) -> UUID | str | int | list[int] | None:
    """获取任务的单个字段值

    Args:
        task_id: 任务ID
        field_name: 字段名

    Returns:
        字段值，如果任务不存在则返回None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_SESSION_TASK_FIELD1),
            {"id_value": task_id, "field_name_1": field_name},
        )
        return result.scalar()


async def get_task_fields(
    task_id: UUID,
    field_names: list[_TASK_FIELD_NAMES],
) -> dict[_TASK_FIELD_NAMES, UUID | str | int | list[int]] | None:
    """获取任务的多个字段值

    Args:
        task_id: 任务ID
        field_names: 字段名列表

    Returns:
        字段值字典，如果任务不存在则返回None
    """
    field_count = len(field_names)

    if field_count == 0:
        return {}
    elif field_count == 1:
        sql = QUERY_SESSION_TASK_FIELD1
    elif field_count == 2:
        sql = QUERY_SESSION_TASK_FIELD2
    elif field_count == 3:
        sql = QUERY_SESSION_TASK_FIELD3
    elif field_count == 4:
        sql = QUERY_SESSION_TASK_FIELD4
    else:
        raise ValueError(f"Unsupported field count: {field_count}")

    params: dict[str, Any] = {"id_value": task_id}
    for i, field_name in enumerate(field_names, 1):
        sql = sql.replace(f":field_name_{i}", field_name)  # type: ignore[union-attr]

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(sql), params)
        row = result.first()

        if row is None:
            return None

        return {field_names[i]: row[i] for i in range(len(field_names))}


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
