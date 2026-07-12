from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import text

from api.sql_utils import ASYNC_SQL_ENGINE
from api.sql_utils.utils import parse_sql_file

sql_file_path = Path(__file__).parent / "U2ASessionBranch.sql"

sql_statements = parse_sql_file(sql_file_path)

CREATE_TABLE = sql_statements.get_list("CreateSessionBranchesTable")
CREATE_SESSION_BRANCH_TRIGGERS = sql_statements.get_list("CreateSessionBranchTriggers")

INSERT_SESSION_BRANCH = sql_statements.get_str("InsertSessionBranch")

UPDATE_SESSION_BRANCH_LEAF_TASK = sql_statements.get_str("UpdateSessionBranchLeafTask")
UPDATE_SESSION_BRANCH_ARCHIVED = sql_statements.get_str("UpdateSessionBranchArchived")

QUERY_SESSION_BRANCH_BY_ID = sql_statements.get_str("QuerySessionBranchById")
QUERY_SESSION_BRANCH_BY_SESSION_AND_NAME = sql_statements.get_str("QuerySessionBranchBySessionAndName")
QUERY_SESSION_BRANCHES_BY_SESSION = sql_statements.get_str("QuerySessionBranchesBySession")
QUERY_SESSION_BRANCH_BY_LEAF_TASK_ID = sql_statements.get_str("QuerySessionBranchByLeafTaskId")
SESSION_BRANCH_EXISTS = sql_statements.get_str("SessionBranchExists")

DELETE_SESSION_BRANCH = sql_statements.get_str("DeleteSessionBranch")
DELETE_SESSION_BRANCHES_BY_SESSION = sql_statements.get_str("DeleteSessionBranchesBySession")


@dataclass
class _U2ASessionBranch:
    """U2A会话分支数据模型，该数据模型尽量不应该被其他模块直接存储或长期持有"""
    id: UUID
    session_id: UUID
    name: str
    created_by: str
    archived: bool
    leaf_task_id: UUID
    created_at: datetime
    updated_at: datetime


@dataclass
class _U2ASessionBranchCreate:
    """创建U2A会话分支的数据模型"""
    session_id: UUID
    name: str
    created_by: str
    leaf_task_id: UUID


@dataclass
class _U2ASessionBranchWithStatus:
    """分支 + 状态标记（单次查询结果）"""
    id: UUID
    name: str
    created_by: str
    archived: bool
    leaf_task_id: UUID
    has_processing_task: bool
    has_pending_task: bool
    has_unprocessed_messages: bool
    last_terminal_status: str | None
    created_at: datetime
    updated_at: datetime



def _row_to_branch(row) -> _U2ASessionBranch:
    """将数据库行转换为分支模型对象"""
    return _U2ASessionBranch(
        id=row.id,
        session_id=row.session_id,
        name=row.name,
        created_by=row.created_by,
        archived=row.archived,
        leaf_task_id=row.leaf_task_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def create_table() -> None:
    """创建U2A会话分支表并设置触发器"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        for stmt in CREATE_TABLE:
            await conn.execute(text(stmt))
        for stmt in CREATE_SESSION_BRANCH_TRIGGERS:
            await conn.execute(text(stmt))
        await conn.commit()


async def insert_branch(branch_data: _U2ASessionBranchCreate) -> UUID:
    """插入新U2A会话分支

    Args:
        branch_data: 分支创建数据

    Returns:
        新分支的id (数据库生成的UUID)
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_SESSION_BRANCH),
            {
                "session_id": branch_data.session_id,
                "name": branch_data.name,
                "created_by": branch_data.created_by,
                "leaf_task_id": branch_data.leaf_task_id,
            },
        )
        await conn.commit()
        return result.scalar()


async def get_branch(branch_id: UUID) -> _U2ASessionBranch | None:
    """获取分支信息

    Args:
        branch_id: 分支ID

    Returns:
        分支信息，如果不存在则返回None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_SESSION_BRANCH_BY_ID),
            {"id_value": branch_id},
        )
        row = result.first()

        if row is None:
            return None

        return _row_to_branch(row)


async def get_branch_by_session_and_name(
    session_id: UUID, name: str
) -> _U2ASessionBranch | None:
    """根据会话ID和分支名称查询分支

    Args:
        session_id: 会话ID
        name: 分支名称

    Returns:
        分支信息，如果不存在则返回None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_SESSION_BRANCH_BY_SESSION_AND_NAME),
            {"session_id_value": session_id, "name_value": name},
        )
        row = result.first()

        if row is None:
            return None

        return _row_to_branch(row)


async def get_branches_by_session(session_id: UUID) -> list[_U2ASessionBranch]:
    """查询会话下的所有分支

    Args:
        session_id: 会话ID

    Returns:
        分支列表，按创建时间排序
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_SESSION_BRANCHES_BY_SESSION),
            {"session_id_value": session_id},
        )
        rows = result.fetchall()

        return [_row_to_branch(row) for row in rows]


async def get_branch_by_leaf_task_id(task_id: UUID) -> _U2ASessionBranch | None:
    """根据叶子任务ID查询分支

    Args:
        task_id: 叶子任务ID

    Returns:
        分支信息，如果不存在则返回None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_SESSION_BRANCH_BY_LEAF_TASK_ID),
            {"leaf_task_id_value": task_id},
        )
        row = result.first()

        if row is None:
            return None

        return _row_to_branch(row)


async def update_branch_leaf_task(branch_id: UUID, new_leaf_task_id: UUID) -> bool:
    """更新分支的叶子任务ID

    Args:
        branch_id: 分支ID
        new_leaf_task_id: 新的叶子任务ID

    Returns:
        更新是否成功
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_SESSION_BRANCH_LEAF_TASK),
            {"id_value": branch_id, "leaf_task_id_value": new_leaf_task_id},
        )
        await conn.commit()
        return result.rowcount > 0


async def update_branch_archived(branch_id: UUID, archived: bool) -> bool:
    """更新分支的归档状态

    Args:
        branch_id: 分支ID
        archived: 是否归档

    Returns:
        更新是否成功
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_SESSION_BRANCH_ARCHIVED),
            {"id_value": branch_id, "archived_value": archived},
        )
        await conn.commit()
        return result.rowcount > 0



async def delete_branch(branch_id: UUID) -> bool:
    """删除分支

    Args:
        branch_id: 分支ID

    Returns:
        删除是否成功（如果分支不存在，返回False）
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(DELETE_SESSION_BRANCH),
            {"id_value": branch_id},
        )
        await conn.commit()
        return result.rowcount > 0


async def delete_branches_by_session(session_id: UUID) -> bool:
    """删除指定会话的所有分支

    Args:
        session_id: 会话ID

    Returns:
        删除是否成功
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(DELETE_SESSION_BRANCHES_BY_SESSION),
            {"session_id_value": session_id},
        )
        await conn.commit()
        return result.rowcount > 0


QUERY_BRANCHES_WITH_STATUS = sql_statements.get_str("QueryBranchesWithStatus")


def _row_to_branch_with_status(row) -> _U2ASessionBranchWithStatus:
    """将数据库行转换为带状态标记的分支模型"""
    return _U2ASessionBranchWithStatus(
        id=row.branch_id,
        name=row.name,
        created_by=row.created_by,
        archived=row.archived,
        leaf_task_id=row.leaf_task_id,
        has_processing_task=row.has_processing_task,
        has_pending_task=row.has_pending_task,
        has_unprocessed_messages=row.has_unprocessed_messages,
        last_terminal_status=row.last_terminal_status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def get_branches_with_status(session_id: UUID) -> list[_U2ASessionBranchWithStatus]:
    """单次查询获取会话所有分支及其状态标记。

    返回分支列表，包含每个分支路径上是否有 processing/pending 任务、
    是否有未处理的用户消息等状态标记。按 created_at 排序。

    Args:
        session_id: 会话ID

    Returns:
        带状态标记的分支列表
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_BRANCHES_WITH_STATUS),
            {"session_id_value": session_id},
        )
        return [_row_to_branch_with_status(row) for row in result.fetchall()]
