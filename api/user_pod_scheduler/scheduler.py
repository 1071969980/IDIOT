"""用户 Pod 调度器核心逻辑"""

import logfire
from uuid import UUID
from datetime import datetime

from api.juiceFS.creator import check_juicefs_formatted, create_juicefs_for_user
from api.juiceFS.string_utils import get_string_var, StringVarName
from api.redis import distributed_lock
from api.redis.lock_names import LockNames
from api.user_pod_scheduler.constants import PodStatus, POD_CREATION_TIMEOUT_SECONDS
from api.user_pod_scheduler.k8s_resources import (
    create_juicefs_secret,
    create_storage_class,
    create_pvc,
    create_user_pod,
    wait_for_pod_ready,
    get_pod_status,
    delete_user_k8s_resources,
)
from api.user_pod_scheduler.sql_stat.utils import (
    insert_record,
    query_record_by_user_id,
    query_record_lifetime,
    update_heartbeat,
    update_status,
    update_status_and_unload,
    _UserPodRecordCreate,
)
from api.logger.logger import log_span


def _make_response(
    success: bool,
    message: str,
    pod_name: str,
    status: str,
    is_new: bool
) -> dict:
    """构造统一格式的响应字典"""
    return {
        "success": success,
        "message": message,
        "pod_name": pod_name,
        "status": status,
        "is_new": is_new
    }


async def _wait_and_handle_ready(
    user_id: UUID,
    pod_name: str,
    is_new: bool,
    timeout: int = POD_CREATION_TIMEOUT_SECONDS
) -> dict:
    """等待 Pod 就绪并处理结果"""
    ready, message = await wait_for_pod_ready(user_id, timeout)

    if ready:
        await update_status(user_id, PodStatus.RUNNING)
        return _make_response(
            success=True,
            message="Pod created and running",
            pod_name=pod_name,
            status=PodStatus.RUNNING,
            is_new=is_new
        )
    else:
        await update_status(user_id, PodStatus.ERROR, message)
        return _make_response(
            success=False,
            message=f"Pod creation failed: {message}",
            pod_name=pod_name,
            status=PodStatus.ERROR,
            is_new=is_new
        )


@log_span("创建/拉起用户 Pod", args_captured_as_tags=["user_id"])
@distributed_lock(lambda bound: LockNames.user_pod_schedule(bound.arguments['user_id']), timeout=300)
async def create_or_start_user_pod(user_id: UUID | str) -> dict:
    """创建或拉起用户 Pod

    返回:
        {
            "success": bool,
            "message": str,
            "pod_name": str,
            "status": str,
            "is_new": bool  # 是否是新创建的
        }
    """
    user_id = UUID(str(user_id)) if isinstance(user_id, str) else user_id

    # 1. 检查是否已有记录
    existing_record = await query_record_by_user_id(user_id)
    pod_name = get_string_var(StringVarName.K8S_User_POD_Name, user_id)

    if existing_record:
        if existing_record.status == PodStatus.RUNNING:
            return _make_response(
                success=True,
                message="Pod already running",
                pod_name=pod_name,
                status=existing_record.status,
                is_new=False
            )
        elif existing_record.status == PodStatus.CREATING:
            # Pod 正在创建中，跳过资源创建，直接等待就绪
            logfire.info(f"Pod is being created, waiting for ready: {user_id}")
            return await _wait_and_handle_ready(user_id, pod_name, is_new=False)

    # 2. 检查并初始化 JuiceFS
    if not await check_juicefs_formatted(user_id):
        logfire.info(f"JuiceFS not formatted for user {user_id}, initializing...")
        if not await create_juicefs_for_user(user_id):
            return _make_response(
                success=False,
                message="Failed to initialize JuiceFS",
                pod_name=pod_name,
                status=PodStatus.ERROR,
                is_new=True
            )

    # 3. 创建数据库记录（状态：creating）
    if not existing_record:
        await insert_record(_UserPodRecordCreate(
            user_id=user_id,
            status=PodStatus.CREATING,
            pod_name=pod_name,
        ))
    else:
        await update_status(user_id, PodStatus.CREATING)
        await update_heartbeat(user_id)

    # 4. 创建 K8S 资源
    try:
        # 4.1 创建 Secret
        if not await create_juicefs_secret(user_id):
            await update_status(user_id, PodStatus.ERROR, "Failed to create secret")
            return _make_response(
                success=False,
                message="Failed to create K8S secret",
                pod_name=pod_name,
                status=PodStatus.ERROR,
                is_new=True
            )

        # 4.2 创建 StorageClass
        if not await create_storage_class(user_id):
            await update_status(user_id, PodStatus.ERROR, "Failed to create storage class")
            return _make_response(
                success=False,
                message="Failed to create storage class",
                pod_name=pod_name,
                status=PodStatus.ERROR,
                is_new=True
            )

        # 4.3 创建 PVC
        if not await create_pvc(user_id):
            await update_status(user_id, PodStatus.ERROR, "Failed to create PVC")
            return _make_response(
                success=False,
                message="Failed to create PVC",
                pod_name=pod_name,
                status=PodStatus.ERROR,
                is_new=True
            )

        # 4.4 创建 Pod
        if not await create_user_pod(user_id):
            await update_status(user_id, PodStatus.ERROR, "Failed to create pod")
            return _make_response(
                success=False,
                message="Failed to create pod",
                pod_name=pod_name,
                status=PodStatus.ERROR,
                is_new=True
            )

        # 5. 等待 Pod 就绪
        return await _wait_and_handle_ready(user_id, pod_name, is_new=True)

    except Exception as e:
        logfire.error(f"Error creating user pod: {e}")
        await update_status(user_id, PodStatus.ERROR, str(e))
        return _make_response(
            success=False,
            message=f"Internal error: {e}",
            pod_name=pod_name,
            status=PodStatus.ERROR,
            is_new=True
        )


@log_span("查询用户 Pod 状态", args_captured_as_tags=["user_id"])
async def get_user_pod_status(user_id: UUID | str) -> dict:
    """查询用户 Pod 状态"""
    user_id = UUID(str(user_id)) if isinstance(user_id, str) else user_id

    # 查询数据库记录
    record = await query_record_by_user_id(user_id)

    # 查询 K8S Pod 状态
    k8s_status = await get_pod_status(user_id)

    # 查询生存时间
    lifetime = await query_record_lifetime(user_id) if record else None

    return {
        "user_id": str(user_id),
        "database_record": {
            "status": record.status if record else None,
            "create_at": record.create_at.isoformat() if record else None,
            "heartbeat_at": record.heartbeat_at.isoformat() if record else None,
            "unload_at": record.unload_at.isoformat() if record and record.unload_at else None,
            "error_message": record.error_message if record else None,
        },
        "k8s_status": k8s_status,
        "lifetime_seconds": lifetime.lifetime_seconds if lifetime else None,
        "juicefs_mount_path": "/juice" if k8s_status.get("exists") else None,
    }


@log_span("刷新用户 Pod 心跳", args_captured_as_tags=["user_id"])
async def refresh_user_pod_heartbeat(user_id: UUID | str) -> bool:
    """刷新用户 Pod 心跳"""
    user_id = UUID(str(user_id)) if isinstance(user_id, str) else user_id
    return await update_heartbeat(user_id)


@log_span("卸载用户 Pod", args_captured_as_tags=["user_id"])
@distributed_lock(lambda bound: LockNames.user_pod_schedule(bound.arguments['user_id']), timeout=300)
async def unload_user_pod(user_id: UUID | str) -> bool:
    """卸载用户 Pod"""
    user_id = UUID(str(user_id)) if isinstance(user_id, str) else user_id

    # 更新状态为 stopping
    await update_status(user_id, PodStatus.STOPPING)

    # 删除 K8S 资源
    success = await delete_user_k8s_resources(user_id)

    if success:
        await update_status_and_unload(user_id, PodStatus.STOPPED)
    else:
        await update_status(user_id, PodStatus.ERROR, "Failed to delete K8S resources")

    return success