from dataclasses import dataclass
from typing import Literal
from uuid import UUID
from datetime import datetime
from sqlalchemy import text

from api.sql_orm_models import ASYNC_SQL_ENGINE
from api.sql_orm_models.utils import parse_sql_file
from pathlib import Path


sql_file_path = Path(__file__).parent / "U2AUserMsg.sql"

sql_statements = parse_sql_file(sql_file_path)

CREATE_USER_MESSAGES_TABLE = sql_statements["CreateUserMessagesTable"]
CREATE_USER_MESSAGE_TRIGGERS = sql_statements["CreateUserMessageTriggers"]

INSERT_USER_MESSAGE = sql_statements["InsertUserMessage"]

UPDATE_USER_MESSAGE_1 = sql_statements["UpdateUserMessage1"]
UPDATE_USER_MESSAGE_2 = sql_statements["UpdateUserMessage2"]
UPDATE_USER_MESSAGE_3 = sql_statements["UpdateUserMessage3"]
UPDATE_USER_MESSAGE_STATUS_BY_IDS = sql_statements["UpdateUserMessageStatusByIds"]
UPDATE_USER_MESSAGE_SESSION_TASK_BY_IDS = sql_statements["UpdateUserMessageSessionTaskByIds"]

CHECK_USER_MESSAGE_EXISTS = sql_statements["UserMessageExists"]
QUERY_USER_MESSAGE_BY_ID = sql_statements["QueryUserMessageById"]
QUERY_USER_MESSAGES_BY_SESSION = sql_statements["QueryUserMessagesBySession"]
QUERY_USER_MESSAGES_BY_USER = sql_statements["QueryUserMessagesByUser"]
QUERY_USER_MESSAGE_FIELD_1 = sql_statements["QueryUserMessageField1"]
QUERY_USER_MESSAGE_FIELD_2 = sql_statements["QueryUserMessageField2"]
QUERY_USER_MESSAGE_FIELD_3 = sql_statements["QueryUserMessageField3"]
QUERY_USER_MESSAGE_FIELD_4 = sql_statements["QueryUserMessageField4"]
DELETE_USER_MESSAGE = sql_statements["DeleteUserMessage"]
DELETE_USER_MESSAGES_BY_SESSION = sql_statements["DeleteUserMessagesBySession"]
GET_NEXT_USER_MESSAGE_SEQ_INDEX = sql_statements["GetNextUserMessageSeqIndex"]


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
    created_at: datetime
    updated_at: datetime


@dataclass
class _U2AUserMessageCreate:
    """创建U2A用户消息的数据模型"""
    user_id: UUID
    session_id: UUID
    seq_index: int
    message_type: str
    content: str
    status: str
    session_task_id: UUID | None = None


@dataclass
class _U2AUserMessageUpdate:
    """更新U2A用户消息的数据模型"""
    message_id: UUID
    fields: dict[
        Literal["user_id", "session_id", "seq_index", "message_type", "content", "status", "session_task_id"],
        UUID | str | int
    ]


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
                "seq_index": message_data.seq_index,
                "message_type": message_data.message_type,
                "content": message_data.content,
                "status": message_data.status,
                "session_task_id": message_data.session_task_id,
            }
        )
        await conn.commit()
        return result.scalar()


async def get_next_user_message_seq_index(session_id: UUID) -> int:
    """获取会话的下一条消息序列索引

    Args:
        session_id: 会话ID

    Returns:
        下一条消息的序列索引
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(GET_NEXT_USER_MESSAGE_SEQ_INDEX),
            {"session_id": session_id}
        )
        return result.scalar() or 0


async def update_user_message_fields(update_data: _U2AUserMessageUpdate) -> bool:
    """更新消息字段

    Args:
        update_data: 消息更新数据

    Returns:
        更新是否成功
    """
    field_count = len(update_data.fields)

    if field_count == 0:
        return False
    elif field_count == 1:
        sql = UPDATE_USER_MESSAGE_1
    elif field_count == 2:
        sql = UPDATE_USER_MESSAGE_2
    elif field_count == 3:
        sql = UPDATE_USER_MESSAGE_3
    else:
        raise ValueError(f"Unsupported field count: {field_count}")

    params = {"id_value": update_data.message_id}
    for i, (field, value) in enumerate(update_data.fields.items(), 1):
        params[f"field_name_{i}"] = field
        params[f"field_value_{i}"] = value

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(sql), params)
        await conn.commit()
        return result.rowcount > 0


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
                created_at=row.created_at,
                updated_at=row.updated_at,
            ) for row in rows
        ]


async def get_user_message_field(
    message_id: UUID,
    field_name: Literal["id", "user_id", "session_id", "seq_index", "message_type", "content", "status", "session_task_id", "created_at", "updated_at"],
) -> UUID | str | int | None:
    """获取消息的单个字段值

    Args:
        message_id: 消息ID
        field_name: 字段名

    Returns:
        字段值，如果消息不存在则返回None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_USER_MESSAGE_FIELD_1),
            {"id_value": message_id, "field_name_1": field_name}
        )
        return result.scalar()


async def get_user_message_fields(
    message_id: UUID,
    field_names: list[Literal["id", "user_id", "session_id", "seq_index", "message_type", "content", "status", "session_task_id", "created_at", "updated_at"]],
) -> dict[
    Literal["id", "user_id", "session_id", "seq_index", "message_type", "content", "status", "session_task_id", "created_at", "updated_at"],
    UUID | str | int,
] | None:
    """获取消息的多个字段值

    Args:
        message_id: 消息ID
        field_names: 字段名列表

    Returns:
        字段值字典，如果消息不存在则返回None
    """
    field_count = len(field_names)

    if field_count == 0:
        return {}
    elif field_count == 1:
        sql = QUERY_USER_MESSAGE_FIELD_1
    elif field_count == 2:
        sql = QUERY_USER_MESSAGE_FIELD_2
    elif field_count == 3:
        sql = QUERY_USER_MESSAGE_FIELD_3
    elif field_count == 4:
        sql = QUERY_USER_MESSAGE_FIELD_4
    else:
        raise ValueError(f"Unsupported field count: {field_count}")

    params = {"id_value": message_id}
    for i, field_name in enumerate(field_names, 1):
        params[f"field_name_{i}"] = field_name

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(sql), params)
        row = result.first()

        if row is None:
            return None

        return {field_names[i]: row[i] for i in range(len(field_names))}


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
        "complete",
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
            text(UPDATE_USER_MESSAGE_STATUS_BY_IDS),
            {
                "status_value": new_status,
                "ids_list": tuple(message_ids),
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
            text(UPDATE_USER_MESSAGE_SESSION_TASK_BY_IDS),
            {
                "session_task_id_value": session_task_id,
                "ids_list": tuple(message_ids),
            }
        )
        await conn.commit()
        return result.rowcount