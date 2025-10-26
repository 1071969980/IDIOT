from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import text

from api.sql_orm_models import ASYNC_SQL_ENGINE
from api.sql_orm_models.utils import now_str, parse_sql_file

sql_file_path = Path(__file__).parent / "a2a_session_task.sql"

sql_statements = parse_sql_file(sql_file_path)

CREATE_TABLE = sql_statements["CreateTable"]
CREATE_TRIGGER = sql_statements["CreateTrigger"]

INSERT_SESSION_TASK = sql_statements["InsertSessionTask"]

UPDATE_SESSION_TASK1 = sql_statements["UpdateSessionTask1"]
UPDATE_SESSION_TASK2 = sql_statements["UpdateSessionTask2"]
UPDATE_SESSION_TASK3 = sql_statements["UpdateSessionTask3"]
UPDATE_SESSION_TASK_STATUS = sql_statements["UpdateSessionTaskStatus"]

SESSION_TASK_EXISTS = sql_statements["SessionTaskExists"]
QUERY_SESSION_TASK_BY_ID = sql_statements["QuerySessionTaskById"]
QUERY_SESSION_TASKS_BY_SESSION = sql_statements["QuerySessionTasksBySession"]
QUERY_SESSION_TASK_BY_SESSION_AND_STATUS = sql_statements["QuerySessionTaskBySessionAndStatus"]
QUERY_SESSION_TASKS_BY_STATUS = sql_statements["QuerySessionTasksByStatus"]
QUERY_SESSION_TASK_FIELD1 = sql_statements["QuerySessionTaskField1"]
QUERY_SESSION_TASK_FIELD2 = sql_statements["QuerySessionTaskField2"]
QUERY_SESSION_TASK_FIELD3 = sql_statements["QuerySessionTaskField3"]
QUERY_SESSION_TASK_FIELD4 = sql_statements["QuerySessionTaskField4"]
DELETE_SESSION_TASK = sql_statements["DeleteSessionTask"]
DELETE_SESSION_TASKS_BY_SESSION = sql_statements["DeleteSessionTasksBySession"]

CHECK_SESSION_HAS_TASK_WITH_STATUS = sql_statements["CheckSessionHasTaskWithStatus"]
CHECK_SESSION_HAS_TASK_WITH_STATUSES = sql_statements["CheckSessionHasTaskWithStatuses"]
GET_SESSION_TASK_STATUS_COUNTS = sql_statements["GetSessionTaskStatusCounts"]

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
    created_at: str
    updated_at: str


@dataclass
class _A2ASessionTaskCreate:
    """创建A2A会话任务的数据模型"""
    session_id: UUID
    status: str | None = None
    priority: int | None = None
    parmas: dict[str, Any] | None = None
    conclusion: str | None = None
    extra_result_data: dict[str, Any] | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class _A2ASessionTaskUpdate:
    """更新A2A会话任务的数据模型"""
    task_id: UUID
    fields: dict[
        Literal[
            "session_id", "status", "priority", "parmas",
            "conclusion", "extra_result_data", "created_at", "updated_at",
        ],
        UUID | str | int | dict[str, Any] | None,
    ]


async def create_table() -> None:
    """创建A2A会话任务表并设置触发器"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        await conn.execute(text(CREATE_TABLE))
        await conn.execute(text(CREATE_TRIGGER))
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
    if task_data.created_at is None:
        task_data.created_at = now_str()
    if task_data.updated_at is None:
        task_data.updated_at = now_str()

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_SESSION_TASK),
            {
                "session_id": task_data.session_id,
                "status": task_data.status,
                "priority": task_data.priority,
                "parmas": task_data.parmas,
                "conclusion": task_data.conclusion,
                "extra_result_data": task_data.extra_result_data,
            },
        )
        await conn.commit()
        return result.scalar()


async def update_task_fields(update_data: _A2ASessionTaskUpdate) -> bool:
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

    params = {"id_value": update_data.task_id}
    for i, (field, value) in enumerate(update_data.fields.items(), 1):
        params[f"field_name_{i}"] = field
        params[f"field_value_{i}"] = value

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(sql), params)
        await conn.commit()
        return result.rowcount > 0


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
            text(UPDATE_SESSION_TASK_STATUS),
            {
                "id_value": task_id,
                "status_value": new_status,
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
        result = await conn.execute(text(SESSION_TASK_EXISTS), {"id_value": task_id})
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
        result = await conn.execute(text(QUERY_SESSION_TASK_BY_ID), {"id_value": task_id})
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
        result = await conn.execute(text(QUERY_SESSION_TASKS_BY_SESSION), {"session_id_value": session_id})
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
        result = await conn.execute(text(QUERY_SESSION_TASK_BY_SESSION_AND_STATUS),
                                     {"session_id_value": session_id, "status_value": status})
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
                created_at=row.created_at,
                updated_at=row.updated_at,
            ) for row in rows
        ]


async def get_tasks_by_status(status: str) -> list[_A2ASessionTask]:
    """根据会话ID和状态获取任务

    Args:
        session_id: 会话ID
        status: 状态值

    Returns:
        任务列表
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_SESSION_TASKS_BY_STATUS),
                                     {"status_value": status})
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
                created_at=row.created_at,
                updated_at=row.updated_at,
            ) for row in rows
        ]


async def get_task_field(
    task_id: UUID,
    field_name: Literal[
        "id", "session_id", "status", "priority", "parmas",
        "conclusion", "extra_result_data", "created_at", "updated_at",
    ],
) -> UUID | str | int | dict[str, Any] | None:
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
    field_names: list[
        Literal[
            "id", "session_id", "status", "priority", "parmas",
            "conclusion", "extra_result_data", "created_at", "updated_at",
        ]
    ],
) -> dict[Literal["id", "session_id", "status", "priority", "parmas", "conclusion", "extra_result_data", "created_at", "updated_at"], UUID | str | int | dict[str, Any] | None] | None:
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

    params = {"id_value": task_id}
    for i, field_name in enumerate(field_names, 1):
        params[f"field_name_{i}"] = field_name

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
    # 将状态列表转换为SQL IN子句格式
    status_values = ",".join([f"'{status}'" for status in statuses])

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(CHECK_SESSION_HAS_TASK_WITH_STATUSES),
            {"session_id_value": session_id, ":status_values": status_values},
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
