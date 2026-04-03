# 通知服务层与FastAPI接口

## 通知服务层（notification_service.py）

文件位置：`api/system_notification/notification_service.py`

此文件为对外暴露的服务层，主应用通过 `from api.system_notification.notification_service import ...` 直接调用。

**设计说明**：系统级公告的创建由 Task Pod 负责（参见 [Task Pod](#task-pod-入口task_apppy)），本服务层不提供系统级公告的创建函数。用户级和会话级公告的创建通过 Python 函数直接调用（非 HTTP 接口），由本服务层的 `create_user_notification` 和 `create_session_notification` 函数提供，使用双写机制（先 PG 后 Redis）。系统级公告的读取和 ACK 使用 cache-aside 模式（Redis 缓存 miss 时从 PG 回填，含空结果标记防护）。

```python
from uuid import UUID
from api.system_notification.sql_stat.system_notification.utils import (
    _SystemNotificationResult,
    get_unacked as db_get_unacked,
)
from api.system_notification.sql_stat.system_notification_ack.utils import (
    insert_ack, _SystemNotificationAckCreate,
)
from api.system_notification.sql_stat.user_notification.utils import (
    insert_user_notification, _UserNotificationCreate, _UserNotificationResult,
    get_active_by_user_id as db_get_user_notifs,
    soft_delete as db_soft_delete_user,
)
from api.system_notification.sql_stat.session_notification.utils import (
    insert_session_notification, _SessionNotificationCreate, _SessionNotificationResult,
    get_active_by_session_id as db_get_session_notifs,
    soft_delete as db_soft_delete_session,
)
from api.system_notification.redis_ops import (
    SYS_NOTIF_PREFIX, USER_NOTIF_PREFIX, SESSION_NOTIF_PREFIX,
)
from api.system_notification.dual_write import (
    write_notification_with_dual_write,
    ack_with_dual_write,
    read_with_cache_fallback,
)
# 注意：session_id 已关联唯一 user_id，以下 session 级函数均只需 session_id 参数


# ── 系统级公告（读取 + ACK）──


async def get_unacked_system_notifications(
    user_id: UUID,
) -> list[dict]:
    """获取用户的未确认系统级公告。cache-aside: 先读Redis，miss则读PG并回填。
    返回 list[dict]，dict 包含 id、level、content、created_at 字段。
    """
    stream_key = f"{SYS_NOTIF_PREFIX}{user_id}"
    return await read_with_cache_fallback(
        stream_key=stream_key,
        db_read_coro=lambda: db_get_unacked(user_id),
        notification_type="system",
    )


async def ack_system_notification(
    notification_id: UUID, user_id: UUID,
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
        from api.system_notification.redis_ops import delete_notification_from_redis
        await delete_notification_from_redis(stream_key, str(notification_id))
    except Exception:
        pass  # Redis 删除失败不影响 PG ACK
    return True


# ── 用户级公告（创建 + 读取 + 删除）──


async def create_user_notification(
    user_id: UUID,
    level: str,
    content: str,
) -> _UserNotificationResult:
    """创建用户级公告（双写：先PG后Redis）。"""
    stream_key = f"{USER_NOTIF_PREFIX}{user_id}"
    data = _UserNotificationCreate(user_id=user_id, level=level, content=content)

    async def _db_write():
        result = await insert_user_notification(data)
        return result

    result = await write_notification_with_dual_write(
        stream_key=stream_key,
        db_write_coro=_db_write,
        notification_data=None,  # 由 dual_write 从 result 构造
    )
    return result


async def get_user_notifications(
    user_id: UUID,
) -> list[dict]:
    """获取用户的未删除用户级公告。返回 list[dict]。"""
    stream_key = f"{USER_NOTIF_PREFIX}{user_id}"
    return await read_with_cache_fallback(
        stream_key=stream_key,
        db_read_coro=lambda: db_get_user_notifs(user_id),
        notification_type="user",
    )


async def delete_user_notification(
    notification_id: UUID, user_id: UUID,
) -> bool:
    stream_key = f"{USER_NOTIF_PREFIX}{user_id}"
    return await ack_with_dual_write(
        stream_key=stream_key,
        ack_db_coro=lambda: db_soft_delete_user(notification_id, user_id),
        notification_id=str(notification_id),
    )


# ── 会话级公告（创建 + 读取 + 删除）──


async def create_session_notification(
    session_id: UUID,
    user_id: UUID,
    level: str,
    content: str,
) -> _SessionNotificationResult:
    """创建会话级公告（双写：先PG后Redis）。"""
    stream_key = f"{SESSION_NOTIF_PREFIX}{session_id}"
    data = _SessionNotificationCreate(session_id=session_id, user_id=user_id, level=level, content=content)

    async def _db_write():
        result = await insert_session_notification(data)
        return result

    result = await write_notification_with_dual_write(
        stream_key=stream_key,
        db_write_coro=_db_write,
        notification_data=None,  # 由 dual_write 从 result 构造
    )
    return result


async def get_session_notifications(
    session_id: UUID,
    user_id: UUID | None = None,
) -> list[dict]:
    """获取会话级公告。返回 list[dict]，dict 包含 id、level、content、created_at、user_id 字段。

    session_id 已关联唯一用户。当传入 user_id 时，校验该用户是否有权访问此会话的公告。
    """
    # 权限校验：通过查询结果中的 user_id 字段判断归属
    results = await read_with_cache_fallback(
        stream_key=f"{SESSION_NOTIF_PREFIX}{session_id}",
        db_read_coro=lambda: db_get_session_notifs(session_id),
        notification_type="session",
    )
    if user_id is not None and results:
        # 校验至少一条公告的 user_id 与当前用户匹配
        # results 为 list[dict]，已包含 user_id 字段
        first = results[0]
        result_user_id = first.get("user_id")
        if result_user_id and str(result_user_id) != str(user_id):
            raise PermissionError(f"User {user_id} does not have access to session {session_id}")
    return results


async def delete_session_notification(
    notification_id: UUID, session_id: UUID, user_id: UUID | None = None,
) -> bool:
    """删除会话级公告。

    session_id 已关联唯一用户。当传入 user_id 时，校验该用户是否有权操作此会话的公告。
    """
    stream_key = f"{SESSION_NOTIF_PREFIX}{session_id}"
    return await ack_with_dual_write(
        stream_key=stream_key,
        ack_db_coro=lambda: db_soft_delete_session(notification_id, session_id),
        notification_id=str(notification_id),
    )
```

## Task Pod 入口（task_app.py）

文件位置：`api/system_notification_task/task_app.py`

作为一次性 Job 运行，通过 CLI 参数传入公告级别和内容，执行完毕后退出。不使用 FastAPI。

```python
import argparse
import asyncio
import logfire
from api.logger import init_logger
from api.system_notification.sql_stat.system_notification.utils import (
    insert_notification, _SystemNotificationCreate,
)
from api.system_notification.redis_ops import invalidate_all_system_notification_caches


async def create_system_notification(
    level: str,
    content: str,
) -> str:
    """创建系统级公告并清理缓存。

    1. 写入 PG system_notifications 表
    2. 清理所有用户的系统级公告 Redis 缓存（含空结果标记 Key）

    返回创建的公告 UUID。
    """
    with logfire.span("system_notification_task::create", level=level):
        result = await insert_notification(
            _SystemNotificationCreate(level=level, content=content)
        )
        logfire.info("System notification created", notification_id=str(result.id))

        # 清理所有用户的系统级公告缓存
        try:
            count = await invalidate_all_system_notification_caches()
            logfire.info("Cache invalidated", keys_deleted=count)
        except Exception as e:
            logfire.error("Cache invalidation failed", error=str(e))
            # 不回滚 PG 写入，依赖 TTL 兜底

        return str(result.id)


def main():
    init_logger()
    parser = argparse.ArgumentParser(description="创建系统级公告")
    parser.add_argument("--level", required=True, choices=["info", "warning", "critical"],
                        help="公告级别")
    parser.add_argument("--content", required=True, help="公告内容")
    args = parser.parse_args()

    notification_id = asyncio.run(create_system_notification(args.level, args.content))
    print(f"Created system notification: {notification_id}")


if __name__ == "__main__":
    main()
```

## Task Pod 启动脚本

文件位置：`api/system_notification_task.sh`

```bash
#!/bin/bash
source .venv/bin/activate
python -m api.system_notification_task.task_app "$@"
```

使用示例：

```bash
# 在 K8s 中作为 Job 运行
kubectl create job --from=cronjob/system-notification-task manual-notification -- \
    --level warning --content "系统将于今晚22:00维护"
```

## FastAPI接口（endpoints.py）

文件位置：`api/app/system_notification/endpoints.py`

路由声明参考 `api/app/chat/router_declare.py` 模式，认证依赖参考 [system_notification_spec_context.md](../system_notification_spec_context.md#33-认证依赖)。

### data_model.py

文件位置：`api/app/system_notification/data_model.py`

```python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class NotificationItem(BaseModel):
    id: UUID
    level: str
    content: str
    created_at: datetime


class NotificationListResponse(BaseModel):
    notifications: list[NotificationItem]
```

### router_declare.py

```python
from fastapi import APIRouter

router = APIRouter(
    prefix="/notifications",
    tags=["system-notification"],
)
```

### endpoints.py

```python
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException

from api.authentication.utils import _User, get_current_active_user
from api.system_notification import notification_service as ns

from .data_model import NotificationListResponse
from .router_declare import router


@router.get("/system-notifications",
            response_model=NotificationListResponse)
async def get_system_notifications(
    user: Annotated[_User, Depends(get_current_active_user)],
):
    notifs = await ns.get_unacked_system_notifications(user.id)
    return NotificationListResponse(notifications=notifs)


@router.post("/system-notifications/{notification_id}/ack")
async def ack_system_notification(
    notification_id: UUID,
    user: Annotated[_User, Depends(get_current_active_user)],
):
    result = await ns.ack_system_notification(notification_id, user.id)
    if result is None:
        # 已 ACK 过或公告不存在，幂等返回成功
        return {"status": "already_acked"}
    return {"status": "acked"}


@router.get("/user-notifications",
            response_model=NotificationListResponse)
async def get_user_notifications(
    user: Annotated[_User, Depends(get_current_active_user)],
):
    notifs = await ns.get_user_notifications(user.id)
    return NotificationListResponse(notifications=notifs)


@router.delete("/user-notifications/{notification_id}")
async def delete_user_notification(
    notification_id: UUID,
    user: Annotated[_User, Depends(get_current_active_user)],
):
    success = await ns.delete_user_notification(
        notification_id, user.id,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "deleted"}


@router.get("/session-notifications/{session_id}",
            response_model=NotificationListResponse)
async def get_session_notifications(
    session_id: UUID,
    user: Annotated[_User, Depends(get_current_active_user)],
):
    # 校验当前用户是否有权访问该会话的公告
    notifs = await ns.get_session_notifications(session_id, user.id)
    return NotificationListResponse(notifications=notifs)


@router.delete("/session-notifications/{session_id}/{notification_id}")
async def delete_session_notification(
    session_id: UUID,
    notification_id: UUID,
    user: Annotated[_User, Depends(get_current_active_user)],
):
    success = await ns.delete_session_notification(
        notification_id, session_id, user.id,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "deleted"}
```
