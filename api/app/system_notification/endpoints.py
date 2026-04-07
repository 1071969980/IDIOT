from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException

from api.authentication.utils import _User, get_current_active_user
from api.system_notification import notification_service as ns
from api.system_notification.types import InternalNotification

from .data_model import NotificationItem, NotificationListResponse, PaginationParams
from .router_declare import router


def _to_item(n: InternalNotification) -> NotificationItem:
    """将 InternalNotification 转为 API 响应模型。"""
    return NotificationItem(
        id=n.id,
        level=n.level,
        content=n.content,
        created_at=n.created_at,
    )


def _apply_pagination(
    items: list[InternalNotification], pagination: PaginationParams | None
) -> list[NotificationItem]:
    """将 InternalNotification 列表转为 NotificationItem，可选分页。"""
    if pagination is not None and pagination.limit is not None:
        offset = pagination.offset or 0
        items = items[offset : offset + pagination.limit]
    return [_to_item(n) for n in items]


@router.get(
    "/system-notifications",
    response_model=NotificationListResponse,
)
async def list_system_notifications(
    user: Annotated[_User, Depends(get_current_active_user)],
    pagination: PaginationParams | None = None,
):
    """获取当前用户未确认的系统级公告。"""
    notifs = await ns.get_unacked_system_notifications(user.id)
    return NotificationListResponse(notifications=_apply_pagination(notifs, pagination))


@router.post("/system-notifications/{notification_id}/ack")
async def acknowledge_system_notification(
    notification_id: UUID,
    user: Annotated[_User, Depends(get_current_active_user)],
):
    """确认系统级公告。幂等：已 ACK 过返回 already_acked。"""
    result = await ns.ack_system_notification(notification_id, user.id)
    if result is None:
        return {"status": "already_acked"}
    return {"status": "acked"}


@router.get(
    "/user-notifications",
    response_model=NotificationListResponse,
)
async def list_user_notifications(
    user: Annotated[_User, Depends(get_current_active_user)],
    pagination: PaginationParams | None = None,
):
    """获取当前用户的未删除用户级公告。"""
    notifs = await ns.get_user_notifications(user.id)
    return NotificationListResponse(notifications=_apply_pagination(notifs, pagination))


@router.post("/user-notifications/{notification_id}/ack")
async def acknowledge_user_notification(
    notification_id: UUID,
    user: Annotated[_User, Depends(get_current_active_user)],
):
    """确认用户级公告（软删除）。"""
    success = await ns.ack_user_notification(notification_id, user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "acked"}


@router.get(
    "/session-notifications/{session_id}",
    response_model=NotificationListResponse,
)
async def list_session_notifications(
    session_id: UUID,
    user: Annotated[_User, Depends(get_current_active_user)],
    pagination: PaginationParams | None = None,
):
    """获取指定会话的公告（校验当前用户是否有权访问）。"""
    notifs = await ns.get_session_notifications(session_id, user.id)
    return NotificationListResponse(notifications=_apply_pagination(notifs, pagination))


@router.post("/session-notifications/{session_id}/{notification_id}/ack")
async def acknowledge_session_notification(
    session_id: UUID,
    notification_id: UUID,
    user: Annotated[_User, Depends(get_current_active_user)],
):
    """确认会话级公告（软删除，校验用户归属）。"""
    success = await ns.ack_session_notification(notification_id, session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "acked"}
