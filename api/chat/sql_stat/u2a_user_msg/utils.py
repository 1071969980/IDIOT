from dataclasses import dataclass
from typing import Literal
from uuid import UUID
from datetime import datetime
from sqlalchemy import bindparam, text

from api.sql_utils import ASYNC_SQL_ENGINE
from api.sql_utils.utils import parse_sql_file
from pathlib import Path
from sqlalchemy.dialects.postgresql import UUID as SQLTYPE_UUID

sql_file_path = Path(__file__).parent / "U2AUserMsg.sql"

sql_statements = parse_sql_file(sql_file_path)

CREATE_USER_MESSAGES_TABLE = sql_statements.get_list("CreateUserMessagesTable")
CREATE_USER_MESSAGE_TRIGGERS = sql_statements.get_list("CreateUserMessageTriggers")

INSERT_USER_MESSAGE = sql_statements.get_str("InsertUserMessage")

UPDATE_USER_MESSAGE_STATUS_BY_IDS = sql_statements.get_str("UpdateUserMessageStatusByIds")
UPDATE_USER_MESSAGE_SESSION_TASK_BY_IDS = sql_statements.get_str("UpdateUserMessageSessionTaskByIds")

CHECK_USER_MESSAGE_EXISTS = sql_statements.get_str("UserMessageExists")
QUERY_USER_MESSAGE_BY_ID = sql_statements.get_str("QueryUserMessageById")
QUERY_USER_MESSAGES_BY_SESSION = sql_statements.get_str("QueryUserMessagesBySession")
QUERY_USER_MESSAGES_BY_SESSION_WITH_LIMIT = sql_statements.get_str("QueryUserMessagesBySessionWithLimit")
QUERY_USER_MESSAGES_BY_SESSION_WITH_LIMIT_AND_SEQ_INDEX = sql_statements.get_str("QueryUserMessagesBySessionWithLimitAndSeqIndex")
QUERY_USER_MESSAGES_BY_USER = sql_statements.get_str("QueryUserMessagesByUser")
DELETE_USER_MESSAGE = sql_statements.get_str("DeleteUserMessage")
DELETE_USER_MESSAGES_BY_SESSION = sql_statements.get_str("DeleteUserMessagesBySession")
QUERY_USER_MESSAGES_BY_SESSION_TASK_ID = sql_statements.get_str("QueryUserMessagesBySessionTaskId")
QUERY_USER_MESSAGES_BY_SESSION_TASK_IDS = sql_statements.get_str("QueryUserMessagesBySessionTaskIds")
QUERY_USER_MESSAGES_BY_SESSION_TASK_IDS_WITH_LIMIT = sql_statements.get_str("QueryUserMessagesBySessionTaskIdsWithLimit")
QUERY_USER_MESSAGES_BY_SESSION_TASK_IDS_WITH_LIMIT_AND_SEQ_INDEX = sql_statements.get_str("QueryUserMessagesBySessionTaskIdsWithLimitAndSeqIndex")


@dataclass
class _U2AUserMessage:
    """U2A用户消息数据模型"""
    id: UUID
    user_id: UUID
    session_id: UUID
    seq_index: int
    message_type: str
    content: str
    status: str
    session_task_id: UUID | None
    process_priority: int
    present_priority: int
    created_at: datetime
    updated_at: datetime


@dataclass
class _U2AUserMessageCreate:
    """创建U2A用户消息的数据模型"""
    user_id: UUID
    session_id: UUID
    message_type: str
    content: str
    status: str
    session_task_id: UUID | None = None
    process_priority: int = 30
    present_priority: int = 30


async def create_table() -> None:
    """创建U2A消息表并设置触发器"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        # await conn.execute(text(CREATE_USER_MESSAGES_TABLE))
        for stmt in CREATE_USER_MESSAGES_TABLE:
            await conn.execute(text(stmt))
        for stmt in CREATE_USER_MESSAGE_TRIGGERS:
            await conn.execute(text(stmt))
        await conn.commit()


async def insert_user_message(message_data: _U2AUserMessageCreate) -> UUID:
    """插入新U2A用户消息

    Args:
        message_data: 消息创建数据

    Returns:
        新消息的ID
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_USER_MESSAGE),
            {
                "user_id": message_data.user_id,
                "session_id": message_data.session_id,
                "message_type": message_data.message_type,
                "content": message_data.content,
                "status": message_data.status,
                "session_task_id": message_data.session_task_id,
                "process_priority": message_data.process_priority,
                "present_priority": message_data.present_priority,
            }
        )
        await conn.commit()
        return result.scalar()


async def check_user_message_exists(message_id: UUID) -> bool:
    """检查消息是否存在

    Args:
        message_id: 消息ID

    Returns:
        消息是否存在
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(CHECK_USER_MESSAGE_EXISTS), {"id_value": message_id})
        count = result.scalar()
        return count > 0


async def get_user_message_by_id(message_id: UUID) -> _U2AUserMessage | None:
    """获取消息信息

    Args:
        message_id: 消息ID

    Returns:
        消息信息，如果不存在则返回None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_USER_MESSAGE_BY_ID), {"id_value": message_id})
        row = result.first()

        if row is None:
            return None

        return _U2AUserMessage(
            id=row.id,
            user_id=row.user_id,
            session_id=row.session_id,
            seq_index=row.seq_index,
            message_type=row.message_type,
            content=row.content,
            status=row.status,
            session_task_id=row.session_task_id,
            process_priority=row.process_priority,
            present_priority=row.present_priority,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


async def get_user_messages_by_session(session_id: UUID) -> list[_U2AUserMessage]:
    """根据会话ID获取所有消息

    Args:
        session_id: 会话ID

    Returns:
        消息列表
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_USER_MESSAGES_BY_SESSION), {"session_id_value": session_id})
        rows = result.fetchall()

        return [
            _U2AUserMessage(
                id=row.id,
                user_id=row.user_id,
                session_id=row.session_id,
                seq_index=row.seq_index,
                message_type=row.message_type,
                content=row.content,
                status=row.status,
                session_task_id=row.session_task_id,
                process_priority=row.process_priority,
                present_priority=row.present_priority,
                created_at=row.created_at,
                updated_at=row.updated_at,
            ) for row in rows
        ]


async def get_user_messages_by_session_with_limit(session_id: UUID, limit: int) -> list[_U2AUserMessage]:
    """根据会话ID获取限定数量的消息

    Args:
        session_id: 会话ID
        limit: 返回消息的最大数量

    Returns:
        消息列表
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_USER_MESSAGES_BY_SESSION_WITH_LIMIT),
            {
                "session_id_value": session_id,
                "limit_value": limit,
            }
        )
        rows = result.fetchall()

        return [
            _U2AUserMessage(
                id=row.id,
                user_id=row.user_id,
                session_id=row.session_id,
                seq_index=row.seq_index,
                message_type=row.message_type,
                content=row.content,
                status=row.status,
                session_task_id=row.session_task_id,
                process_priority=row.process_priority,
                present_priority=row.present_priority,
                created_at=row.created_at,
                updated_at=row.updated_at,
            ) for row in rows
        ]


async def get_user_messages_by_session_with_limit_and_seq_index(
    session_id: UUID, limit: int, max_seq_index: int
) -> list[_U2AUserMessage]:
    """根据会话ID、限定数量和seq_index条件获取消息

    Args:
        session_id: 会话ID
        limit: 返回消息的最大数量
        max_seq_index: 最大seq_index值（只返回小于此值的消息）

    Returns:
        消息列表
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_USER_MESSAGES_BY_SESSION_WITH_LIMIT_AND_SEQ_INDEX),
            {
                "session_id_value": session_id,
                "limit_value": limit,
                "max_seq_index_value": max_seq_index,
            }
        )
        rows = result.fetchall()

        return [
            _U2AUserMessage(
                id=row.id,
                user_id=row.user_id,
                session_id=row.session_id,
                seq_index=row.seq_index,
                message_type=row.message_type,
                content=row.content,
                status=row.status,
                session_task_id=row.session_task_id,
                process_priority=row.process_priority,
                present_priority=row.present_priority,
                created_at=row.created_at,
                updated_at=row.updated_at,
            ) for row in rows
        ]


async def get_user_messages_by_user(user_id: UUID) -> list[_U2AUserMessage]:
    """根据用户ID获取所有消息

    Args:
        user_id: 用户ID

    Returns:
        消息列表
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_USER_MESSAGES_BY_USER), {"user_id_value": user_id})
        rows = result.fetchall()

        return [
            _U2AUserMessage(
                id=row.id,
                user_id=row.user_id,
                session_id=row.session_id,
                seq_index=row.seq_index,
                message_type=row.message_type,
                content=row.content,
                status=row.status,
                session_task_id=row.session_task_id,
                process_priority=row.process_priority,
                present_priority=row.present_priority,
                created_at=row.created_at,
                updated_at=row.updated_at,
            ) for row in rows
        ]


async def delete_user_message(message_id: UUID) -> bool:
    """删除消息

    Args:
        message_id: 消息ID

    Returns:
        删除是否成功（如果消息不存在，返回False）
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(DELETE_USER_MESSAGE), {"id_value": message_id})
        await conn.commit()
        return result.rowcount > 0


async def delete_user_messages_by_session(session_id: UUID) -> bool:
    """删除指定会话的所有消息

    Args:
        session_id: 会话ID

    Returns:
        删除是否成功
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(DELETE_USER_MESSAGES_BY_SESSION), {"session_id_value": session_id})
        await conn.commit()
        return result.rowcount > 0


async def update_user_message_status_by_ids(
    message_ids: list[UUID],
    new_status: Literal[
        "agent_working_for_user",
        "waiting_agent_ack_user",
        "completed",
        "error",
    ],
) -> int:
    """根据消息ID批量更新消息状态

    Args:
        message_ids: 消息ID列表
        new_status: 新的状态值

    Returns:
        更新的消息数量
    """
    if not message_ids:
        return 0

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_USER_MESSAGE_STATUS_BY_IDS).bindparams(
                bindparam("ids_list", expanding=True, type_=SQLTYPE_UUID)
            ),
            {
                "status_value": new_status,
                "ids_list": message_ids,
            }
        )
        await conn.commit()
        return result.rowcount


async def update_user_message_session_task_by_ids(
    message_ids: list[UUID],
    session_task_id: UUID | None,
) -> int:
    """根据消息ID批量更新消息的session_task_id

    Args:
        message_ids: 消息ID列表
        session_task_id: 新的session_task_id值，如果为None则清除关联

    Returns:
        更新的消息数量
    """
    if not message_ids:
        return 0

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_USER_MESSAGE_SESSION_TASK_BY_IDS).bindparams(
                bindparam("ids_list", expanding=True, type_=SQLTYPE_UUID)
            ),
            {
                "session_task_id_value": session_task_id,
                "ids_list": message_ids,
            }
        )
        await conn.commit()
        return result.rowcount


async def get_user_messages_by_session_task_id(session_task_id: UUID) -> list[_U2AUserMessage]:
    """根据会话任务ID获取所有关联消息

    Args:
        session_task_id: 会话任务ID

    Returns:
        消息列表，按 seq_index 升序排列
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_USER_MESSAGES_BY_SESSION_TASK_ID),
            {"session_task_id_value": session_task_id},
        )
        rows = result.fetchall()
        return [
            _U2AUserMessage(
                id=row.id,
                user_id=row.user_id,
                session_id=row.session_id,
                seq_index=row.seq_index,
                message_type=row.message_type,
                content=row.content,
                status=row.status,
                session_task_id=row.session_task_id,
                process_priority=row.process_priority,
                present_priority=row.present_priority,
                created_at=row.created_at,
                updated_at=row.updated_at,
            ) for row in rows
        ]


async def get_user_messages_by_session_task_ids(
    task_ids: list[UUID],
) -> list[_U2AUserMessage]:
    """根据多个 session_task_id 批量查询用户消息

    Args:
        task_ids: session_task_id 列表

    Returns:
        消息列表，按 seq_index 升序排列
    """
    if not task_ids:
        return []
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_USER_MESSAGES_BY_SESSION_TASK_IDS).bindparams(
                bindparam("task_ids_list", expanding=True, type_=SQLTYPE_UUID),
            ),
            {"task_ids_list": task_ids},
        )
        rows = result.fetchall()
        return [
            _U2AUserMessage(
                id=row.id,
                user_id=row.user_id,
                session_id=row.session_id,
                seq_index=row.seq_index,
                message_type=row.message_type,
                content=row.content,
                status=row.status,
                session_task_id=row.session_task_id,
                process_priority=row.process_priority,
                present_priority=row.present_priority,
                created_at=row.created_at,
                updated_at=row.updated_at,
            ) for row in rows
        ]


async def get_user_messages_by_session_task_ids_with_limit(
    task_ids: list[UUID],
    limit: int,
) -> list[_U2AUserMessage]:
    """根据多个 session_task_id 批量查询用户消息（带数量限制）

    Args:
        task_ids: session_task_id 列表
        limit: 返回消息的最大数量

    Returns:
        消息列表，按 seq_index 降序排列（最新的在前）
    """
    if not task_ids:
        return []
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_USER_MESSAGES_BY_SESSION_TASK_IDS_WITH_LIMIT).bindparams(
                bindparam("task_ids_list", expanding=True, type_=SQLTYPE_UUID),
            ),
            {"task_ids_list": task_ids, "limit_value": limit},
        )
        rows = result.fetchall()
        return [
            _U2AUserMessage(
                id=row.id,
                user_id=row.user_id,
                session_id=row.session_id,
                seq_index=row.seq_index,
                message_type=row.message_type,
                content=row.content,
                status=row.status,
                session_task_id=row.session_task_id,
                process_priority=row.process_priority,
                present_priority=row.present_priority,
                created_at=row.created_at,
                updated_at=row.updated_at,
            ) for row in rows
        ]


async def get_user_messages_by_session_task_ids_with_limit_and_seq_index(
    task_ids: list[UUID],
    limit: int,
    max_seq_index: int,
) -> list[_U2AUserMessage]:
    """根据多个 session_task_id 批量查询用户消息（带数量限制和 seq_index 过滤）

    Args:
        task_ids: session_task_id 列表
        limit: 返回消息的最大数量
        max_seq_index: 最大 seq_index 值（只返回 seq_index 小于此值的消息）

    Returns:
        消息列表，按 seq_index 降序排列（最新的在前）
    """
    if not task_ids:
        return []
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_USER_MESSAGES_BY_SESSION_TASK_IDS_WITH_LIMIT_AND_SEQ_INDEX).bindparams(
                bindparam("task_ids_list", expanding=True, type_=SQLTYPE_UUID),
            ),
            {"task_ids_list": task_ids, "limit_value": limit, "max_seq_index_value": max_seq_index},
        )
        rows = result.fetchall()
        return [
            _U2AUserMessage(
                id=row.id,
                user_id=row.user_id,
                session_id=row.session_id,
                seq_index=row.seq_index,
                message_type=row.message_type,
                content=row.content,
                status=row.status,
                session_task_id=row.session_task_id,
                process_priority=row.process_priority,
                present_priority=row.present_priority,
                created_at=row.created_at,
                updated_at=row.updated_at,
            ) for row in rows
        ]