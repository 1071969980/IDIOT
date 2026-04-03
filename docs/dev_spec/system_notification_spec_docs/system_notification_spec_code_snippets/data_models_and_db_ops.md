# Python数据模型与数据库操作（utils.py）

各 `utils.py` 的数据模型与数据库操作遵循项目已有规范，参考 `api/user_pod_scheduler/sql_stat/utils.py`。查询函数通过 `_row_to_record` 辅助函数将 Row 转换为 dataclass 返回。

## system_notification/utils.py

文件位置：`api/system_notification/sql_stat/system_notification/utils.py`

```python
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlalchemy import text

from api.sql_utils import ASYNC_SQL_ENGINE
from api.sql_utils.utils import parse_sql_file

sql_file_path = Path(__file__).parent / "SystemNotification.sql"
sql_statements = parse_sql_file(sql_file_path)

CREATE_TABLE = sql_statements["CreateTablesAndIndexes"]  # list[str]
INSERT_NOTIFICATION = sql_statements["InsertNotification"]
GET_UNACKED = sql_statements["GetUnackedNotifications"]
GET_ALL_NOTIFICATIONS = sql_statements["GetAllNotifications"]


@dataclass
class _SystemNotificationCreate:
    """创建系统公告的数据模型"""
    level: str
    content: str


@dataclass
class _SystemNotificationResult:
    """系统公告查询结果"""
    id: UUID
    level: str
    content: str
    created_at: datetime
    updated_at: datetime


async def create_table() -> None:
    """创建表和索引（含触发器）"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        for stmt in CREATE_TABLE:
            await conn.execute(text(stmt))
        await conn.commit()


async def insert_notification(
    data: _SystemNotificationCreate,
) -> _SystemNotificationResult:
    """插入系统公告，返回完整记录"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_NOTIFICATION),
            {"level": data.level, "content": data.content},
        )
        await conn.commit()
        row = result.first()
        return _SystemNotificationResult(
            id=row.id, level=row.level, content=row.content,
            created_at=row.created_at, updated_at=row.updated_at,
        )


async def get_unacked(user_id: UUID) -> list[_SystemNotificationResult]:
    """获取用户未 ACK 的系统级公告列表（NOT EXISTS 子查询）"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(GET_UNACKED), {"user_id": user_id}
        )
        rows = result.fetchall()
        return [
            _SystemNotificationResult(
                id=row.id, level=row.level, content=row.content,
                created_at=row.created_at, updated_at=row.updated_at,
            )
            for row in rows
        ]
```

## system_notification_ack/utils.py

文件位置：`api/system_notification/sql_stat/system_notification_ack/utils.py`

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlalchemy import text

from api.sql_utils import ASYNC_SQL_ENGINE
from api.sql_utils.utils import parse_sql_file

sql_file_path = Path(__file__).parent / "SystemNotificationAck.sql"
sql_statements = parse_sql_file(sql_file_path)

CREATE_TABLE = sql_statements["CreateTablesAndIndexes"]  # list[str]
INSERT_ACK = sql_statements["InsertAck"]
GET_UNACKED_IDS = sql_statements["GetUnackedNotifications"]


@dataclass
class _SystemNotificationAckCreate:
    notification_id: UUID
    user_id: UUID


async def insert_ack(
    data: _SystemNotificationAckCreate,
) -> Optional[UUID]:
    """插入 ACK 记录。ON CONFLICT DO NOTHING 保证幂等性。

    返回值：
    - UUID: 首次 ACK 成功，返回生成的记录 ID
    - None: 该用户已 ACK 过该公告（重复 ACK，幂等返回 None）
    """
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_ACK),
            {"notification_id": data.notification_id, "user_id": data.user_id},
        )
        await conn.commit()
        row = result.first()
        return row.id if row else None
```

## user_notification/utils.py

文件位置：`api/system_notification/sql_stat/user_notification/utils.py`

```python
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlalchemy import text

from api.sql_utils import ASYNC_SQL_ENGINE
from api.sql_utils.utils import parse_sql_file

sql_file_path = Path(__file__).parent / "UserNotification.sql"
sql_statements = parse_sql_file(sql_file_path)

CREATE_TABLE = sql_statements["CreateTablesAndIndexes"]  # list[str]
INSERT_NOTIFICATION = sql_statements["InsertNotification"]
GET_ACTIVE_BY_USER_ID = sql_statements["GetActiveByUserId"]
SOFT_DELETE = sql_statements["SoftDelete"]


@dataclass
class _UserNotificationCreate:
    user_id: UUID
    level: str
    content: str


@dataclass
class _UserNotificationResult:
    id: UUID
    user_id: UUID
    level: str
    content: str
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime]


async def insert_user_notification(
    data: _UserNotificationCreate,
) -> _UserNotificationResult:
    """插入用户级公告，返回完整记录"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_NOTIFICATION),
            {"user_id": data.user_id, "level": data.level, "content": data.content},
        )
        await conn.commit()
        row = result.first()
        return _UserNotificationResult(
            id=row.id, user_id=row.user_id, level=row.level,
            content=row.content, created_at=row.created_at,
            updated_at=row.updated_at, deleted_at=row.deleted_at,
        )


async def get_active_by_user_id(user_id: UUID) -> list[_UserNotificationResult]:
    """获取用户的未删除用户级公告列表"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(GET_ACTIVE_BY_USER_ID), {"user_id": user_id}
        )
        rows = result.fetchall()
        return [
            _UserNotificationResult(
                id=row.id, user_id=row.user_id, level=row.level,
                content=row.content, created_at=row.created_at,
                updated_at=row.updated_at, deleted_at=row.deleted_at,
            )
            for row in rows
        ]


async def soft_delete(notification_id: UUID, user_id: UUID) -> bool:
    """软删除用户级公告。返回是否成功删除。"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(SOFT_DELETE),
            {"notification_id": notification_id, "user_id": user_id},
        )
        await conn.commit()
        return result.rowcount > 0
```

## session_notification/utils.py

文件位置：`api/system_notification/sql_stat/session_notification/utils.py`

```python
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlalchemy import text

from api.sql_utils import ASYNC_SQL_ENGINE
from api.sql_utils.utils import parse_sql_file

sql_file_path = Path(__file__).parent / "SessionNotification.sql"
sql_statements = parse_sql_file(sql_file_path)

CREATE_TABLE = sql_statements["CreateTablesAndIndexes"]  # list[str]
INSERT_NOTIFICATION = sql_statements["InsertNotification"]
GET_ACTIVE_BY_SESSION_ID = sql_statements["GetActiveBySessionId"]
SOFT_DELETE = sql_statements["SoftDelete"]


@dataclass
class _SessionNotificationCreate:
    session_id: UUID
    user_id: UUID
    level: str
    content: str


@dataclass
class _SessionNotificationResult:
    id: UUID
    session_id: UUID
    user_id: UUID
    level: str
    content: str
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime]


async def insert_session_notification(
    data: _SessionNotificationCreate,
) -> _SessionNotificationResult:
    """插入会话级公告，返回完整记录"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(INSERT_NOTIFICATION),
            {
                "session_id": data.session_id, "user_id": data.user_id,
                "level": data.level, "content": data.content,
            },
        )
        await conn.commit()
        row = result.first()
        return _SessionNotificationResult(
            id=row.id, session_id=row.session_id, user_id=row.user_id,
            level=row.level, content=row.content, created_at=row.created_at,
            updated_at=row.updated_at, deleted_at=row.deleted_at,
        )


async def get_active_by_session_id(session_id: UUID) -> list[_SessionNotificationResult]:
    """获取会话的未删除会话级公告列表。session_id 已关联唯一用户，只需 session_id 参数。"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(GET_ACTIVE_BY_SESSION_ID), {"session_id": session_id}
        )
        rows = result.fetchall()
        return [
            _SessionNotificationResult(
                id=row.id, session_id=row.session_id, user_id=row.user_id,
                level=row.level, content=row.content, created_at=row.created_at,
                updated_at=row.updated_at, deleted_at=row.deleted_at,
            )
            for row in rows
        ]


async def soft_delete(notification_id: UUID, session_id: UUID) -> bool:
    """软删除会话级公告。同时校验 session_id 确保归属关系正确。返回是否成功删除。"""
    async with ASYNC_SQL_ENGINE.connect() as conn:
        result = await conn.execute(
            text(SOFT_DELETE),
            {"notification_id": notification_id, "session_id": session_id},
        )
        await conn.commit()
        return result.rowcount > 0
```
