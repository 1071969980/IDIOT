import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID
from datetime import datetime

from sqlalchemy import text, bindparam
from sqlalchemy.dialects.postgresql import JSONB, UUID as SQLTYPE_UUID
from api.sql_utils import ASYNC_SQL_ENGINE
from api.sql_utils.utils import parse_sql_file

# Parse SQL file to get SQL statements
sql_statements = parse_sql_file(Path(__file__).parent / "u2a_session_agent_config.sql")


# Extract SQL statements
CREATE_TABLE = sql_statements.get_list("CreateTable")
INSERT_SESSION_CONFIG = sql_statements.get_str("InsertSessionConfig")
UPDATE_SESSION_CONFIG = sql_statements.get_str("UpdateSessionConfig")
UPDATE_SESSION_CONFIG_BY_SESSION_ID = sql_statements.get_str("UpdateSessionConfigBySessionId")
QUERY_SESSION_CONFIG = sql_statements.get_str("QuerySessionConfig")
QUERY_SESSION_CONFIG_BY_SESSION_ID = sql_statements.get_str("QuerySessionConfigBySessionId")
DELETE_SESSION_CONFIG = sql_statements.get_str("DeleteSessionConfig")
DELETE_SESSION_CONFIG_BY_SESSION_ID = sql_statements.get_str("DeleteSessionConfigBySessionId")
SESSION_CONFIG_EXISTS = sql_statements.get_str("SessionConfigExists")
SESSION_CONFIG_EXISTS_BY_SESSION_ID = sql_statements.get_str("SessionConfigExistsBySessionId")


@dataclass
class _U2ASessionAgentConfig:
    """U2A会话配置数据模型"""
    id: UUID
    session_id: UUID
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass
class _U2ASessionAgentConfigCreate:
    """创建U2A会话配置的数据模型"""
    session_id: UUID
    config: dict[str, Any]


@dataclass
class _U2ASessionAgentConfigUpdate:
    """更新U2A会话配置的数据模型"""
    id: UUID | None = None
    session_id: UUID | None = None
    config: dict[str, Any] | None = None


async def create_table() -> None:
    """确保表存在"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        for stat in CREATE_TABLE:
            await conn.execute(text(stat))
        await conn.commit()


async def insert_session_config(
    config_data: _U2ASessionAgentConfigCreate,
) -> UUID:
    """插入新的会话配置

    Args:
        config_data: 会话配置创建数据

    Returns:
        新创建的配置ID
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_SESSION_CONFIG).bindparams(
                bindparam("session_id", type_=SQLTYPE_UUID),
                bindparam("config", type_=JSONB),
            ),
            {
                "session_id": config_data.session_id,
                "config": config_data.config,
            },
        )
        await conn.commit()
        return result.scalar()


async def get_session_config(
    config_id: UUID,
) -> _U2ASessionAgentConfig | None:
    """根据ID获取会话配置

    Args:
        config_id: 配置ID

    Returns:
        会话配置对象, 如果不存在返回None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_SESSION_CONFIG).bindparams(
                bindparam("id_value", type_=SQLTYPE_UUID),
            ),
            {"id_value": config_id},
        )
        row = result.first()

        if row is None:
            return None

        return _U2ASessionAgentConfig(
            id=row.id,
            session_id=row.session_id,
            config=(
                json.loads(row.config)
                if isinstance(row.config, str)
                else row.config
            ),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


async def get_session_config_by_session_id(
    session_id: UUID,
) -> _U2ASessionAgentConfig | None:
    """根据会话ID获取会话配置

    Args:
        session_id: 会话ID

    Returns:
        会话配置对象, 如果不存在返回None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(QUERY_SESSION_CONFIG_BY_SESSION_ID).bindparams(
                bindparam("session_id_value", type_=SQLTYPE_UUID),
            ),
            {"session_id_value": session_id},
        )
        row = result.first()

        if row is None:
            return None

        return _U2ASessionAgentConfig(
            id=row.id,
            session_id=row.session_id,
            config=(
                json.loads(row.config)
                if isinstance(row.config, str)
                else row.config
            ),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


async def update_session_config(
    config_id: UUID,
    config: dict[str, Any],
) -> bool:
    """更新会话配置

    Args:
        config_id: 配置ID
        config: 新的配置数据

    Returns:
        更新是否成功
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_SESSION_CONFIG).bindparams(
                bindparam("id_value", type_=SQLTYPE_UUID),
                bindparam("config", type_=JSONB),
            ),
            {
                "id_value": config_id,
                "config": config,
            },
        )
        await conn.commit()
        return result.rowcount > 0


async def update_session_config_by_session_id(
    session_id: UUID, config: dict[str, Any]
) -> bool:
    """根据会话ID更新会话配置

    Args:
        session_id: 会话ID
        config: 新的配置数据

    Returns:
        更新是否成功
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(UPDATE_SESSION_CONFIG_BY_SESSION_ID).bindparams(
                bindparam("session_id_value", type_=SQLTYPE_UUID),
                bindparam("config", type_=JSONB),
            ),
            {
                "session_id_value": session_id,
                "config": config,
            },
        )
        await conn.commit()
        return result.rowcount > 0


async def delete_session_config(config_id: UUID) -> bool:
    """删除会话配置

    Args:
        config_id: 配置ID

    Returns:
        删除是否成功
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(DELETE_SESSION_CONFIG).bindparams(
                bindparam("id_value", type_=SQLTYPE_UUID),
            ),
            {"id_value": config_id},
        )
        await conn.commit()
        return result.rowcount > 0


async def delete_session_config_by_session_id(session_id: UUID) -> bool:
    """根据会话ID删除会话配置

    Args:
        session_id: 会话ID

    Returns:
        删除是否成功
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(DELETE_SESSION_CONFIG_BY_SESSION_ID).bindparams(
                bindparam("session_id_value", type_=SQLTYPE_UUID),
            ),
            {"session_id_value": session_id},
        )
        await conn.commit()
        return result.rowcount > 0


async def session_config_exists(config_id: UUID) -> bool:
    """检查会话配置是否存在

    Args:
        config_id: 配置ID

    Returns:
        配置是否存在
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(SESSION_CONFIG_EXISTS).bindparams(
                bindparam("id_value", type_=SQLTYPE_UUID),
            ),
            {"id_value": config_id},
        )
        return result.scalar()


async def session_config_exists_by_session_id(session_id: UUID) -> bool:
    """根据会话ID检查会话配置是否存在

    Args:
        session_id: 会话ID

    Returns:
        配置是否存在
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(SESSION_CONFIG_EXISTS_BY_SESSION_ID).bindparams(
                bindparam("session_id_value", type_=SQLTYPE_UUID),
            ),
            {"session_id_value": session_id},
        )
        return result.scalar()