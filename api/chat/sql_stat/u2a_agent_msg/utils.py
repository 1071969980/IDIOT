from dataclasses import dataclass
from typing import Optional, Dict, Any, Union, Literal
from uuid import uuid4
from sqlalchemy import text, Row
from sqlalchemy.ext.asyncio import AsyncConnection

from api.sql_orm_models import ASYNC_SQL_ENGINE
from api.sql_orm_models.utils import parse_sql_file
from pathlib import Path


sql_file_path = Path(__file__).parent / "U2AAgentMsg.sql"

sql_statements = parse_sql_file(sql_file_path)

CREATE_AGENT_MESSAGES_TABLE = sql_statements["CreateAgentMessagesTable"]
CREATE_AGENT_MESSAGE_TRIGGERS = sql_statements["CreateAgentMessageTriggers"]

INSERT_AGENT_MESSAGE = sql_statements["InsertAgentMessage"]

UPDATE_AGENT_MESSAGE_1 = sql_statements["UpdateAgentMessage1"]
UPDATE_AGENT_MESSAGE_2 = sql_statements["UpdateAgentMessage2"]
UPDATE_AGENT_MESSAGE_3 = sql_statements["UpdateAgentMessage3"]
UPDATE_AGENT_MESSAGE_STATUS_BY_UUIDS = sql_statements["UpdateAgentMessageStatusByUuids"]
UPDATE_AGENT_MESSAGE_SESSION_TASK_BY_UUIDS = sql_statements["UpdateAgentMessageSessionTaskByUuids"]

CHECK_AGENT_MESSAGE_EXISTS = sql_statements["AgentMessageExists"]
QUERY_AGENT_MESSAGE_BY_ID = sql_statements["QueryAgentMessageById"]
QUERY_AGENT_MESSAGES_BY_SESSION = sql_statements["QueryAgentMessagesBySession"]
QUERY_AGENT_MESSAGES_BY_USER = sql_statements["QueryAgentMessagesByUser"]
QUERY_AGENT_MESSAGE_FIELD_1 = sql_statements["QueryAgentMessageField1"]
QUERY_AGENT_MESSAGE_FIELD_2 = sql_statements["QueryAgentMessageField2"]
QUERY_AGENT_MESSAGE_FIELD_3 = sql_statements["QueryAgentMessageField3"]
QUERY_AGENT_MESSAGE_FIELD_4 = sql_statements["QueryAgentMessageField4"]
DELETE_AGENT_MESSAGE = sql_statements["DeleteAgentMessage"]
DELETE_AGENT_MESSAGES_BY_SESSION = sql_statements["DeleteAgentMessagesBySession"]
GET_NEXT_AGENT_MESSAGE_SUB_SEQ_INDEX = sql_statements["GetNextAgentMessageSubSeqIndex"]


@dataclass
class _U2AAgentMessage:
    """U2A代理消息数据模型"""
    id: int
    user_id: str
    session_id: str
    sub_seq_index: int
    message_uuid: str
    message_type: str
    content: str
    status: str
    session_task_id: Optional[str]
    created_at: str
    updated_at: str


@dataclass
class _U2AAgentMessageCreate:
    """创建U2A代理消息的数据模型"""
    user_id: str
    session_id: str
    sub_seq_index: int
    message_uuid: str
    message_type: str
    content: str
    status: str
    session_task_id: Optional[str] = None


@dataclass
class _U2AAgentMessageUpdate:
    """更新U2A代理消息的数据模型"""
    message_id: int
    fields: Dict[
        Literal["user_id", "session_id", "sub_seq_index", "message_uuid", "message_type", "content", "status", "session_task_id"],
        Union[str, int]
    ]


async def create_table() -> None:
    """创建U2A代理消息表并设置触发器"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        await conn.execute(text(CREATE_AGENT_MESSAGES_TABLE))
        await conn.execute(text(CREATE_AGENT_MESSAGE_TRIGGERS))
        await conn.commit()


async def insert_agent_message(message_data: _U2AAgentMessageCreate) -> int:
    """插入新U2A代理消息

    Args:
        message_data: 消息创建数据

    Returns:
        新消息的ID
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_AGENT_MESSAGE),
            {
                "user_id": message_data.user_id,
                "session_id": message_data.session_id,
                "sub_seq_index": message_data.sub_seq_index,
                "message_uuid": message_data.message_uuid,
                "message_type": message_data.message_type,
                "content": message_data.content,
                "status": message_data.status,
                "session_task_id": message_data.session_task_id
            }
        )
        await conn.commit()
        return result.lastrowid


async def get_next_agent_message_sub_seq_index(session_id: str, session_task_id: str) -> int:
    """获取会话的下一条代理消息子序列索引

    Args:
        session_id: 会话ID

    Returns:
        下一条代理消息的子序列索引
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(GET_NEXT_AGENT_MESSAGE_SUB_SEQ_INDEX),
            {"session_id": session_id,
             "session_task_id": session_task_id}
        )
        return result.scalar() or 0


async def update_agent_message_fields(update_data: _U2AAgentMessageUpdate) -> bool:
    """更新代理消息字段

    Args:
        update_data: 消息更新数据

    Returns:
        更新是否成功
    """
    field_count = len(update_data.fields)

    if field_count == 0:
        return False
    elif field_count == 1:
        sql = UPDATE_AGENT_MESSAGE_1
    elif field_count == 2:
        sql = UPDATE_AGENT_MESSAGE_2
    elif field_count == 3:
        sql = UPDATE_AGENT_MESSAGE_3
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


async def check_agent_message_exists(message_id: int) -> bool:
    """检查代理消息是否存在

    Args:
        message_id: 消息ID

    Returns:
        消息是否存在
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(CHECK_AGENT_MESSAGE_EXISTS), {"id_value": message_id})
        count = result.scalar()
        return count > 0


async def get_agent_message_by_id(message_id: int) -> Optional[_U2AAgentMessage]:
    """获取代理消息信息

    Args:
        message_id: 消息ID

    Returns:
        消息信息，如果不存在则返回None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_AGENT_MESSAGE_BY_ID), {"id_value": message_id})
        row = result.first()

        if row is None:
            return None

        return _U2AAgentMessage(
            id=row.id,
            user_id=row.user_id,
            session_id=row.session_id,
            sub_seq_index=row.sub_seq_index,
            message_uuid=row.message_uuid,
            message_type=row.message_type,
            content=row.content,
            status=row.status,
            session_task_id=row.session_task_id,
            created_at=row.created_at,
            updated_at=row.updated_at
        )


async def get_agent_messages_by_session(session_id: str) -> list[_U2AAgentMessage]:
    """根据会话ID获取所有代理消息

    Args:
        session_id: 会话ID

    Returns:
        代理消息列表
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_AGENT_MESSAGES_BY_SESSION), {"session_id_value": session_id})
        rows = result.fetchall()

        messages = []
        for row in rows:
            messages.append(_U2AAgentMessage(
                id=row.id,
                user_id=row.user_id,
                session_id=row.session_id,
                sub_seq_index=row.sub_seq_index,
                message_uuid=row.message_uuid,
                message_type=row.message_type,
                content=row.content,
                status=row.status,
                session_task_id=row.session_task_id,
                created_at=row.created_at,
                updated_at=row.updated_at
            ))

        return messages


async def get_agent_messages_by_user(user_id: str) -> list[_U2AAgentMessage]:
    """根据用户ID获取所有代理消息

    Args:
        user_id: 用户ID

    Returns:
        代理消息列表
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_AGENT_MESSAGES_BY_USER), {"user_id_value": user_id})
        rows = result.fetchall()

        messages = []
        for row in rows:
            messages.append(_U2AAgentMessage(
                id=row.id,
                user_id=row.user_id,
                session_id=row.session_id,
                sub_seq_index=row.sub_seq_index,
                message_uuid=row.message_uuid,
                message_type=row.message_type,
                content=row.content,
                status=row.status,
                session_task_id=row.session_task_id,
                created_at=row.created_at,
                updated_at=row.updated_at
            ))

        return messages


async def get_agent_message_field(
    message_id: int,
    field_name: Literal["id", "user_id", "session_id", "sub_seq_index", "message_uuid", "message_type", "content", "status", "session_task_id", "created_at", "updated_at"]
) -> Optional[Union[int, str]]:
    """获取代理消息的单个字段值

    Args:
        message_id: 消息ID
        field_name: 字段名

    Returns:
        字段值，如果消息不存在则返回None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_AGENT_MESSAGE_FIELD_1),
            {"id_value": message_id, "field_name_1": field_name}
        )
        return result.scalar()


async def get_agent_message_fields(
    message_id: int,
    field_names: list[Literal["id", "user_id", "session_id", "sub_seq_index", "message_uuid", "message_type", "content", "status", "session_task_id", "created_at", "updated_at"]]
) -> Optional[Dict[
    Literal["id", "user_id", "session_id", "sub_seq_index", "message_uuid", "message_type", "content", "status", "session_task_id", "created_at", "updated_at"],
    Union[int, str]
]]:
    """获取代理消息的多个字段值

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
        sql = QUERY_AGENT_MESSAGE_FIELD_1
    elif field_count == 2:
        sql = QUERY_AGENT_MESSAGE_FIELD_2
    elif field_count == 3:
        sql = QUERY_AGENT_MESSAGE_FIELD_3
    elif field_count == 4:
        sql = QUERY_AGENT_MESSAGE_FIELD_4
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


async def delete_agent_message(message_id: int) -> bool:
    """删除代理消息

    Args:
        message_id: 消息ID

    Returns:
        删除是否成功（如果消息不存在，返回False）
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(DELETE_AGENT_MESSAGE), {"id_value": message_id})
        await conn.commit()
        return result.rowcount > 0


async def delete_agent_messages_by_session(session_id: str) -> bool:
    """删除指定会话的所有代理消息

    Args:
        session_id: 会话ID

    Returns:
        删除是否成功
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(DELETE_AGENT_MESSAGES_BY_SESSION), {"session_id_value": session_id})
        await conn.commit()
        return result.rowcount > 0


async def update_agent_message_status_by_uuids(
    message_uuids: list[str],
    new_status: Literal["streaming", "stop", "complete", "error"]
) -> int:
    """根据消息UUID批量更新代理消息状态

    Args:
        message_uuids: 消息UUID列表
        new_status: 新的状态值

    Returns:
        更新的消息数量
    """
    if not message_uuids:
        return 0

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_AGENT_MESSAGE_STATUS_BY_UUIDS),
            {
                "status_value": new_status,
                "uuids_list": tuple(message_uuids)
            }
        )
        await conn.commit()
        return result.rowcount


async def update_agent_message_session_task_by_uuids(
    message_uuids: list[str],
    session_task_id: Optional[str]
) -> int:
    """根据消息UUID批量更新代理消息的session_task_id

    Args:
        message_uuids: 消息UUID列表
        session_task_id: 新的session_task_id值，如果为None则清除关联

    Returns:
        更新的消息数量
    """
    if not message_uuids:
        return 0

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_AGENT_MESSAGE_SESSION_TASK_BY_UUIDS),
            {
                "session_task_id_value": session_task_id,
                "uuids_list": tuple(message_uuids)
            }
        )
        await conn.commit()
        return result.rowcount