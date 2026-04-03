from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException

from api.authentication.utils import _User, get_current_active_user
from api.system_notification import notification_service as ns

from .data_model import NotificationListResponse
from .router_declare import router


@router.get(
    "/system-notifications",
    response_model=NotificationListResponse,
)
async def list_system_notifications(
    user: Annotated[_User, Depends(get_current_active_user)],
):
    """获取当前用户未确认的系统级公告。"""
    notifs = await ns.get_unacked_system_notifications(user.id)
    return NotificationListResponse(notifications=notifs)


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
):
    """获取当前用户的未删除用户级公告。"""
    notifs = await ns.get_user_notifications(user.id)
    return NotificationListResponse(notifications=notifs)


@router.delete("/user-notifications/{notification_id}")
async def remove_user_notification(
    notification_id: UUID,
    user: Annotated[_User, Depends(get_current_active_user)],
):
    """删除用户级公告（软删除）。"""
    success = await ns.delete_user_notification(notification_id, user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "deleted"}


@router.get(
    "/session-notifications/{session_id}",
    response_model=NotificationListResponse,
)
async def list_session_notifications(
    session_id: UUID,
    user: Annotated[_User, Depends(get_current_active_user)],
):
    """获取指定会话的公告（校验当前用户是否有权访问）。"""
    notifs = await ns.get_session_notifications(session_id, user.id)
    return NotificationListResponse(notifications=notifs)


@router.delete("/session-notifications/{session_id}/{notification_id}")
async def remove_session_notification(
    session_id: UUID,
    notification_id: UUID,
    user: Annotated[_User, Depends(get_current_active_user)],
):
    """删除会话级公告（软删除，校验用户归属）。"""
    success = await ns.delete_session_notification(
        notification_id, session_id, user.id,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "deleted"}
