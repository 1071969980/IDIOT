"""公告服务层 — 供主应用和 Task Pod 直接调用。

系统级公告的创建由 Task Pod 负责（参见 api/system_notification_task/task_app.py），
本服务层不提供系统级公告的创建函数。

用户级和会话级公告的创建通过 Python 函数直接调用（非 HTTP 接口），
由本服务层的 create_user_notification 和 create_session_notification 函数提供，
使用双写机制（先 PG 后 Redis）。

系统级公告的读取和 ACK 使用 cache-aside 模式
（Redis 缓存 miss 时从 PG 回填，含空结果标记防护）。
"""

from uuid import UUID

from fastapi import HTTPException

from api.system_notification.dual_write import (
    ack_with_dual_write,
    read_with_cache_fallback,
    write_notification_with_dual_write,
)
from api.system_notification.redis_ops import (
    SESSION_NOTIF_PREFIX,
    SYS_NOTIF_PREFIX,
    USER_NOTIF_PREFIX,
    delete_notification_from_redis,
)
from api.system_notification.sql_stat.session_notification.utils import (
    _SessionNotificationCreate,
    get_active_by_session_id as db_get_session_notifs,
    insert_session_notification,
    soft_delete as db_soft_delete_session,
)
from api.system_notification.sql_stat.system_notification_ack.utils import (
    _SystemNotificationAckCreate,
    get_unacked_notifications as db_get_unacked,
    insert_ack,
)
from api.system_notification.sql_stat.user_notification.utils import (
    _UserNotificationCreate,
    get_active_by_user_id as db_get_user_notifs,
    insert_user_notification,
    soft_delete as db_soft_delete_user,
)
from api.system_notification.types import InternalNotification


# ── 系统级公告（读取 + ACK）──


async def get_unacked_system_notifications(
    user_id: UUID,
) -> list[InternalNotification]:
    """获取用户的未确认系统级公告。cache-aside: 先读Redis，miss则读PG并回填。"""
    stream_key = f"{SYS_NOTIF_PREFIX}{user_id}"
    return await read_with_cache_fallback(
        stream_key=stream_key,
        db_read_coro=lambda: db_get_unacked(user_id),
        notification_type="system",
    )


async def ack_system_notification(
    notification_id: UUID,
    user_id: UUID,
) -> bool | None:
    """确认系统级公告。先写PG ACK，再删Redis缓存。

    返回值：
    - True: 首次 ACK 成功
    - None: 该公告已被当前用户 ACK 过（幂等，不报错）
    """
    stream_key = f"{SYS_NOTIF_PREFIX}{user_id}"
    result = await insert_ack(
        _SystemNotificationAckCreate(
            notification_id=notification_id, user_id=user_id
        )
    )
    if result is None:
        # 重复 ACK（ON CONFLICT DO NOTHING）或公告不存在，幂等返回
        return None
    # PG ACK 成功，从 Redis 删除对应消息
    try:
        await delete_notification_from_redis(
            stream_key, str(notification_id)
        )
    except Exception:
        pass  # Redis 删除失败不影响 PG ACK
    return True


# ── 用户级公告（创建 + 读取 + ACK）──


async def create_user_notification(
    user_id: UUID,
    level: str,
    content: str,
):
    """创建用户级公告（双写：先PG后Redis）。"""
    stream_key = f"{USER_NOTIF_PREFIX}{user_id}"
    data = _UserNotificationCreate(
        user_id=user_id, level=level, content=content
    )

    async def _db_write():
        return await insert_user_notification(data)

    result = await write_notification_with_dual_write(
        stream_key=stream_key,
        db_write_coro=_db_write,
        notification_data=None,  # 由 dual_write 从 result 构造
    )
    return result


async def get_user_notifications(
    user_id: UUID,
) -> list[InternalNotification]:
    """获取用户的未删除用户级公告。"""
    stream_key = f"{USER_NOTIF_PREFIX}{user_id}"
    return await read_with_cache_fallback(
        stream_key=stream_key,
        db_read_coro=lambda: db_get_user_notifs(user_id),
        notification_type="user",
    )


async def ack_user_notification(
    notification_id: UUID,
    user_id: UUID,
) -> bool:
    """确认（软删除）用户级公告（双写：先PG软删除，再删Redis）。"""
    stream_key = f"{USER_NOTIF_PREFIX}{user_id}"
    return await ack_with_dual_write(
        stream_key=stream_key,
        ack_db_coro=lambda: db_soft_delete_user(notification_id, user_id),
        notification_id=str(notification_id),
    )


# ── 会话级公告（创建 + 读取 + ACK）──
# 注意：session_id 已关联唯一 user_id，以下会话级函数均只需 session_id 参数


async def create_session_notification(
    session_id: UUID,
    user_id: UUID,
    level: str,
    content: str,
):
    """创建会话级公告（双写：先PG后Redis）。"""
    stream_key = f"{SESSION_NOTIF_PREFIX}{session_id}"
    data = _SessionNotificationCreate(
        session_id=session_id, user_id=user_id, level=level, content=content
    )

    async def _db_write():
        return await insert_session_notification(data)

    result = await write_notification_with_dual_write(
        stream_key=stream_key,
        db_write_coro=_db_write,
        notification_data=None,  # 由 dual_write 从 result 构造
    )
    return result


async def get_session_notifications(
    session_id: UUID,
    user_id: UUID | None = None,
) -> list[InternalNotification]:
    """获取会话级公告。

    session_id 已关联唯一用户。当传入 user_id 时，校验该用户是否有权访问此会话的公告。
    """
    results = await read_with_cache_fallback(
        stream_key=f"{SESSION_NOTIF_PREFIX}{session_id}",
        db_read_coro=lambda: db_get_session_notifs(session_id),
        notification_type="session",
    )
    if user_id is not None and results:
        # 校验至少一条公告的 user_id 与当前用户匹配
        first = results[0]
        if first.user_id and first.user_id != user_id:
            raise HTTPException(
                status_code=403,
                detail=f"User {user_id} does not have access to session {session_id}",
            )
    return results


async def ack_session_notification(
    notification_id: UUID,
    session_id: UUID,
) -> bool:
    """确认（软删除）会话级公告。

    session_id 已关联唯一用户，通过 session_id 校验归属。
    """
    stream_key = f"{SESSION_NOTIF_PREFIX}{session_id}"
    return await ack_with_dual_write(
        stream_key=stream_key,
        ack_db_coro=lambda: db_soft_delete_session(notification_id, session_id),
        notification_id=str(notification_id),
    )
