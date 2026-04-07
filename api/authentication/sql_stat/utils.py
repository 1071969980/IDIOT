from dataclasses import dataclass
from typing import Optional, Dict, Union, Literal
from uuid import UUID
from datetime import datetime
from sqlalchemy import text

from api.sql_utils import ASYNC_SQL_ENGINE
from api.sql_utils.utils import parse_sql_file
from pathlib import Path


sql_file_path = Path(__file__).parent / "UserTable.sql"

sql_statements = parse_sql_file(sql_file_path)

CREATE_TABLE = sql_statements.get_str("CreateTable")

INSERT_USER = sql_statements.get_str("InsertUser")

UPDATE_USER1 = sql_statements.get_str("UpdateUser1")
UPDATE_USER2 = sql_statements.get_str("UpdateUser2")
UPDATE_USER3 = sql_statements.get_str("UpdateUser3")
UPDATE_USER4 = sql_statements.get_str("UpdateUser4")

IS_EXISTS = sql_statements.get_str("IsExists")
QUERY_USER_ID_BY_NAME = sql_statements.get_str("QueryUserIDByName")
QUERY_USER = sql_statements.get_str("QueryUser")
QUERY_USER_BY_USERNAME = sql_statements.get_str("QueryUserByUsername")
DELETE_USER = sql_statements.get_str("DeleteUser")
HARD_DELETE_USER = sql_statements.get_str("HardDeleteUser")


@dataclass
class _User:
    """用户数据模型"""
    id: UUID
    user_name: str
    create_time: datetime
    is_deleted: bool
    hashed_password: str


@dataclass
class _UserCreate:
    """创建用户的数据模型"""
    user_name: str
    hashed_password: str


@dataclass
class _UserUpdate:
    """更新用户的数据模型"""
    id: UUID
    fields: Dict[
        Literal["user_name", "create_time", "is_deleted", "hashed_password"],
        Union[datetime, str, bool]
    ]


async def create_table() -> None:
    """创建用户表"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        await conn.execute(text(CREATE_TABLE))
        await conn.commit()


async def insert_user(user_data: _UserCreate) -> UUID:
    """插入新用户

    Args:
        user_data: 用户创建数据

    Returns:
        新用户的ID
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_USER),
            {
                "user_name": user_data.user_name,
                "hashed_password": user_data.hashed_password
            }
        )
        await conn.commit()

        # 从RETURNING子句获取插入的UUID并转换为正确的类型
        return result.scalar()


async def update_user_fields(update_data: _UserUpdate) -> bool:
    """更新用户字段

    Args:
        update_data: 用户更新数据

    Returns:
        更新是否成功
    """
    field_count = len(update_data.fields)

    if field_count == 0:
        return False
    elif field_count == 1:
        sql = UPDATE_USER1
    elif field_count == 2:
        sql = UPDATE_USER2
    elif field_count == 3:
        sql = UPDATE_USER3
    elif field_count == 4:
        sql = UPDATE_USER4
    else:
        raise ValueError(f"Unsupported field count: {field_count}")

    params = {"id_value": update_data.id}
    for i, (field, value) in enumerate(update_data.fields.items(), 1):
        sql = sql.replace(f":field_name_{i}", field)
        params[f"field_value_{i}"] = value

    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(sql), params)
        await conn.commit()
        return result.rowcount > 0


async def user_exists(id: UUID | str) -> bool:
    """检查用户是否存在

    Args:
        id: 用户ID

    Returns:
        用户是否存在
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(IS_EXISTS), {"id_value": id})
        count = result.scalar()
        return count > 0


async def get_user_id_by_name(user_name: str) -> Optional[UUID]:
    """根据用户名获取用户ID

    Args:
        user_name: 用户名

    Returns:
        用户ID，如果用户不存在或已删除则返回None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_USER_ID_BY_NAME), {"user_name": user_name})
        return result.scalar()


async def get_user_by_username(user_name: str) -> Optional[_User]:
    """根据用户名获取用户信息

    Args:
        user_name: 用户名

    Returns:
        用户信息，如果不存在或已删除则返回None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_USER_BY_USERNAME), {"user_name": user_name})
        row = result.first()

        if row is None:
            return None

        return _User(
            id=row.id,
            user_name=row.user_name,
            create_time=row.create_time,
            is_deleted=row.is_deleted,
            hashed_password=row.hashed_password
        )


async def get_user(id: UUID | str) -> Optional[_User]:
    """获取用户信息

    Args:
        id: 用户ID

    Returns:
        用户信息，如果不存在则返回None
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(QUERY_USER), {"id_value": id})
        row = result.first()

        if row is None:
            return None

        return _User(
            id=row.id,
            user_name=row.user_name,
            create_time=row.create_time,
            is_deleted=row.is_deleted,
            hashed_password=row.hashed_password
        )


async def delete_user(user_id: UUID) -> bool:
    """软删除用户（将is_deleted设置为true）

    Args:
        user_id: 用户ID

    Returns:
        删除是否成功（如果用户不存在或已删除，返回False）
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(DELETE_USER), {"id_value": user_id})
        await conn.commit()
        return result.rowcount > 0


async def hard_delete_user(user_id: UUID) -> bool:
    """硬删除用户（从数据库中永久删除）

    Args:
        user_id: 用户ID

    Returns:
        删除是否成功
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(text(HARD_DELETE_USER), {"id_value": user_id})
        await conn.commit()
        return result.rowcount > 0

