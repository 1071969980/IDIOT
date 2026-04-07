from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID
from datetime import datetime

from sqlalchemy import text, bindparam
from sqlalchemy.dialects.postgresql import JSONB, UUID as SQLTYPE_UUID

from api.sql_utils import ASYNC_SQL_ENGINE
from api.sql_utils.utils import now_str, parse_sql_file

sql_file_path = Path(__file__).parent / "a2a_session_task.sql"

sql_statements = parse_sql_file(sql_file_path)

CREATE_TABLE = sql_statements.get_list("CreateTable")
CREATE_TRIGGER = sql_statements.get_list("CreateTrigger")

INSERT_SESSION_TASK = sql_statements.get_str("InsertSessionTask")

UPDATE_SESSION_TASK_STATUS = sql_statements.get_str("UpdateSessionTaskStatus")
UPDATE_SESSION_TASK_CONCLUSION = sql_statements.get_str("UpdateSessionTaskConclusion")

SESSION_TASK_EXISTS = sql_statements.get_str("SessionTaskExists")
QUERY_SESSION_TASK_BY_ID = sql_statements.get_str("QuerySessionTaskById")
QUERY_SESSION_TASKS_BY_SESSION = sql_statements.get_str("QuerySessionTasksBySession")
QUERY_SESSION_TASK_BY_SESSION_AND_STATUS = sql_statements.get_str("QuerySessionTaskBySessionAndStatus")
QUERY_SESSION_TASKS_BY_STATUS = sql_statements.get_str("QuerySessionTasksByStatus")
DELETE_SESSION_TASK = sql_statements.get_str("DeleteSessionTask")
DELETE_SESSION_TASKS_BY_SESSION = sql_statements.get_str("DeleteSessionTasksBySession")

CHECK_SESSION_HAS_TASK_WITH_STATUS = sql_statements.get_str("CheckSessionHasTaskWithStatus")
CHECK_SESSION_HAS_TASK_WITH_STATUSES = sql_statements.get_str("CheckSessionHasTaskWithStatuses")
GET_SESSION_TASK_STATUS_COUNTS = sql_statements.get_str("GetSessionTaskStatusCounts")

@dataclass
class _A2ASessionTask:
    """A2A会话任务数据模型"""
    id: UUID
    session_id: UUID
    status: str
    priority: int
    parmas: dict[str, Any]
    conclusion: str | None
    extra_result_data: dict[str, Any] | None
    proactive_side: str
    created_at: datetime
    updated_at: datetime


@dataclass
class _A2ASessionTaskCreate:
    """创建A2A会话任务的数据模型"""
    session_id: UUID
    status: str | None = None
    priority: int | None = None
    parmas: dict[str, Any] | None = None
    conclusion: str | None = None
    extra_result_data: dict[str, Any] | None = None
    proactive_side: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None



async def create_table() -> None:
    """创建A2A会话任务表并设置触发器"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        for stmt in CREATE_TABLE:
            await conn.execute(text(stmt))
        for stmt in CREATE_TRIGGER:
            await conn.execute(text(stmt))
        await conn.commit()


async def insert_task(task_data: _A2ASessionTaskCreate) -> UUID:
    """插入新A2A会话任务

    Args:
        task_data: 任务创建数据

    Returns:
        新任务的id (数据库生成的UUID)
    """
    if task_data.status is None:
        task_data.status = "pending"
    if task_data.priority is None:
        task_data.priority = 0
    if task_data.parmas is None:
        task_data.parmas = {}
    if task_data.proactive_side is None:
        task_data.proactive_side = "A"
    if task_data.created_at is None:
        task_data.created_at = now_str()
    if task_data.updated_at is None:
        task_data.updated_at = now_str()

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_SESSION_TASK).bindparams(
                bindparam("session_id", type_=SQLTYPE_UUID),
                bindparam("parmas", type_=JSONB),
                bindparam("extra_result_data", type_=JSONB),
            ),
            {
                "session_id": task_data.session_id,
                "status": task_data.status,
                "priority": task_data.priority,
                "parmas": task_data.parmas,
                "conclusion": task_data.conclusion,
                "extra_result_data": task_data.extra_result_data,
                "proactive_side": task_data.proactive_side,
            },
        )
        await conn.commit()
        return result.scalar()


async def update_task_status(task_id: UUID, new_status: str) -> bool:
    """更新任务状态

    Args:
        task_id: 任务ID
        new_status: 新状态值

    Returns:
        更新是否成功
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_SESSION_TASK_STATUS).bindparams(
                bindparam("id_value", type_=SQLTYPE_UUID),
            ),
            {
                "id_value": task_id,
                "status_value": new_status,
            },
        )
        await conn.commit()
        return result.rowcount > 0


async def update_task_conclusion(task_id: UUID, conclusion: str) -> bool:
    """更新任务结论

    Args:
        task_id: 任务ID
        conclusion: 结论内容

    Returns:
        更新是否成功
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_SESSION_TASK_CONCLUSION).bindparams(
                bindparam("id_value", type_=SQLTYPE_UUID),
            ),
            {
                "id_value": task_id,
                "conclusion_value": conclusion,
            },
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
        result = await conn.execute(
            text(SESSION_TASK_EXISTS).bindparams(
                bindparam("id_value", type_=SQLTYPE_UUID),
            ),
            {"id_value": task_id}
        )
        count = result.scalar()
        return count > 0


async def get_task(task_id: UUID) -> _A2ASessionTask | None:
    """获取任务信息

    Args:
        task_id: 任务ID

    Returns:
        任务信息，如果不存在则返回None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_SESSION_TASK_BY_ID).bindparams(
                bindparam("id_value", type_=SQLTYPE_UUID),
            ),
            {"id_value": task_id}
        )
        row = result.first()

        if row is None:
            return None

        return _A2ASessionTask(
            id=row.id,
            session_id=row.session_id,
            status=row.status,
            priority=row.priority,
            parmas=row.parmas,
            conclusion=row.conclusion,
            extra_result_data=row.extra_result_data,
            proactive_side=row.proactive_side,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


async def get_tasks_by_session(session_id: UUID) -> list[_A2ASessionTask]:
    """根据会话ID获取所有任务

    Args:
        session_id: 会话ID

    Returns:
        任务列表
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_SESSION_TASKS_BY_SESSION).bindparams(
                bindparam("session_id_value", type_=SQLTYPE_UUID),
            ),
            {"session_id_value": session_id}
        )
        rows = result.fetchall()

        return [
            _A2ASessionTask(
                id=row.id,
                session_id=row.session_id,
                status=row.status,
                priority=row.priority,
                parmas=row.parmas,
                conclusion=row.conclusion,
                extra_result_data=row.extra_result_data,
                proactive_side=row.proactive_side,
                created_at=row.created_at,
                updated_at=row.updated_at,
            ) for row in rows
        ]


async def get_tasks_by_session_and_status(session_id: UUID, status: str) -> list[_A2ASessionTask]:
    """根据会话ID和状态获取任务

    Args:
        session_id: 会话ID
        status: 状态值

    Returns:
        任务列表
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_SESSION_TASK_BY_SESSION_AND_STATUS).bindparams(
                bindparam("session_id_value", type_=SQLTYPE_UUID),
            ),
            {"session_id_value": session_id, "status_value": status}
        )
        rows = result.fetchall()
        return [
            _A2ASessionTask(
                id=row.id,
                session_id=row.session_id,
                status=row.status,
                priority=row.priority,
                parmas=row.parmas,
                conclusion=row.conclusion,
                extra_result_data=row.extra_result_data,
                proactive_side=row.proactive_side,
                created_at=row.created_at,
                updated_at=row.updated_at,
            ) for row in rows
        ]


async def get_tasks_by_status(status: str, limit: int = 10) -> list[_A2ASessionTask]:
    """根据会话ID和状态获取任务

    Args:
        session_id: 会话ID
        status: 状态值

    Returns:
        任务列表
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_SESSION_TASKS_BY_STATUS),
                                     {"status_value": status, "limit_value": limit})
        rows = result.fetchall()
        return [
            _A2ASessionTask(
                id=row.id,
                session_id=row.session_id,
                status=row.status,
                priority=row.priority,
                parmas=row.parmas,
                conclusion=row.conclusion,
                extra_result_data=row.extra_result_data,
                proactive_side=row.proactive_side,
                created_at=row.created_at,
                updated_at=row.updated_at,
            ) for row in rows
        ]


async def delete_task(task_id: UUID) -> bool:
    """删除任务

    Args:
        task_id: 任务ID

    Returns:
        删除是否成功（如果任务不存在，返回False）
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(DELETE_SESSION_TASK).bindparams(
                bindparam("id_value", type_=SQLTYPE_UUID),
            ),
            {"id_value": task_id}
        )
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
        result = await conn.execute(
            text(DELETE_SESSION_TASKS_BY_SESSION).bindparams(
                bindparam("session_id_value", type_=SQLTYPE_UUID),
            ),
            {"session_id_value": session_id}
        )
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
            text(CHECK_SESSION_HAS_TASK_WITH_STATUS).bindparams(
                bindparam("session_id_value", type_=SQLTYPE_UUID),
            ),
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
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(CHECK_SESSION_HAS_TASK_WITH_STATUSES).bindparams(
                bindparam("session_id_value", type_=SQLTYPE_UUID),
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
        result = await conn.execute(
            text(GET_SESSION_TASK_STATUS_COUNTS).bindparams(
                bindparam("session_id_value", type_=SQLTYPE_UUID),
            ),
            {"session_id_value": session_id}
        )
        rows = result.fetchall()

        status_counts = {}
        for row in rows:
            status_counts[row.status] = row.count

        return status_counts
