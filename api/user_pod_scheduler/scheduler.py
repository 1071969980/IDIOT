"""用户 Pod 调度器核心逻辑"""

import logfire
from uuid import UUID

from api.juiceFS.creator import check_juicefs_formatted, create_juicefs_for_user
from api.juiceFS.string_utils import get_string_var, StringVarName
from api.redis import distributed_lock
from api.redis.distributed_lock import RedisDistributedLock
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
    delete_user_pod_only,
)
from api.user_pod_scheduler.sql_stat.utils import (
    insert_record,
    query_record_by_user_id_and_image,
    query_records_by_user_id,
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
    is_new: bool,
    image: str = "",
) -> dict:
    """构造统一格式的响应字典"""
    return {
        "success": success,
        "message": message,
        "pod_name": pod_name,
        "status": status,
        "is_new": is_new,
        "image": image,
    }


async def _wait_and_handle_ready(
    user_id: UUID,
    pod_name: str,
    image: str,
    is_new: bool,
    timeout: int = POD_CREATION_TIMEOUT_SECONDS
) -> dict:
    """等待 Pod 就绪并处理结果"""
    ready, message = await wait_for_pod_ready(user_id, timeout, image=image)

    if ready:
        await update_status(user_id, image, PodStatus.RUNNING)
        return _make_response(
            success=True,
            message="Pod created and running",
            pod_name=pod_name,
            status=PodStatus.RUNNING,
            is_new=is_new,
            image=image,
        )
    else:
        await update_status(user_id, image, PodStatus.ERROR, message)
        return _make_response(
            success=False,
            message=f"Pod creation failed: {message}",
            pod_name=pod_name,
            status=PodStatus.ERROR,
            is_new=is_new,
            image=image,
        )


@log_span("创建/拉起用户 Pod", args_captured_as_tags=["user_id", "image"])
@distributed_lock(lambda bound: LockNames.user_pod_schedule(
    bound.arguments['user_id'],
), timeout=300, allow_multi_lock=True)
async def create_or_start_user_pod(user_id: UUID | str, image: str | None = None) -> dict:
    """创建或拉起用户 Pod

    锁策略：外层 user 级锁保护 JuiceFS 资源，内层 user+image 级锁保护 Pod 操作。
    固定获取顺序 user → user+image，避免死锁。

    返回:
        {
            "success": bool,
            "message": str,
            "pod_name": str,
            "status": str,
            "is_new": bool,
            "image": str,
        }
    """
    user_id = UUID(str(user_id)) if isinstance(user_id, str) else user_id
    resolved_image = image or ""

    # 1. 检查是否已有记录（在 user 锁保护下，避免与 unload 竞争 JuiceFS）
    existing_record = await query_record_by_user_id_and_image(user_id, resolved_image)
    pod_name = get_string_var(StringVarName.K8S_User_POD_Name, user_id, image=image)

    if existing_record:
        if existing_record.status == PodStatus.RUNNING:
            return _make_response(
                success=True,
                message="Pod already running",
                pod_name=pod_name,
                status=existing_record.status,
                is_new=False,
                image=resolved_image,
            )
        elif existing_record.status == PodStatus.CREATING:
            # Pod 正在创建中，跳过资源创建，直接等待就绪
            logfire.info(f"Pod is being created, waiting for ready: {user_id}")
            return await _wait_and_handle_ready(user_id, pod_name, resolved_image, is_new=False)

    # 2. 检查并初始化 JuiceFS（per-user，在 user 锁保护下）
    if not await check_juicefs_formatted(user_id):
        logfire.info(f"JuiceFS not formatted for user {user_id}, initializing...")
        if not await create_juicefs_for_user(user_id):
            return _make_response(
                success=False,
                message="Failed to initialize JuiceFS",
                pod_name=pod_name,
                status=PodStatus.ERROR,
                is_new=True,
                image=resolved_image,
            )

    # 3. 创建数据库记录（状态：creating）
    if not existing_record:
        await insert_record(_UserPodRecordCreate(
            user_id=user_id,
            status=PodStatus.CREATING,
            pod_name=pod_name,
            image=resolved_image,
        ))
    else:
        await update_status(user_id, resolved_image, PodStatus.CREATING)
        await update_heartbeat(user_id, resolved_image)

    # 4. 创建 K8S 资源（JuiceFS 在 user 锁保护下，Pod 在 user+image 锁保护下）
    try:
        # 4.1-4.3 创建 JuiceFS K8S 资源（per-user，在 user 锁保护下）
        if not await create_juicefs_secret(user_id):
            await update_status(user_id, resolved_image, PodStatus.ERROR, "Failed to create secret")
            return _make_response(
                success=False,
                message="Failed to create K8S secret",
                pod_name=pod_name,
                status=PodStatus.ERROR,
                is_new=True,
                image=resolved_image,
            )

        if not await create_storage_class(user_id):
            await update_status(user_id, resolved_image, PodStatus.ERROR, "Failed to create storage class")
            return _make_response(
                success=False,
                message="Failed to create storage class",
                pod_name=pod_name,
                status=PodStatus.ERROR,
                is_new=True,
                image=resolved_image,
            )

        if not await create_pvc(user_id):
            await update_status(user_id, resolved_image, PodStatus.ERROR, "Failed to create PVC")
            return _make_response(
                success=False,
                message="Failed to create PVC",
                pod_name=pod_name,
                status=PodStatus.ERROR,
                is_new=True,
                image=resolved_image,
            )

        # 4.4 创建 Pod（per-user+image，在内层 user+image 锁保护下）
        async with RedisDistributedLock(
            key=LockNames.user_pod_schedule_pod(user_id, resolved_image),
            timeout=300,
            allow_multi_lock=True,
        ):
            if not await create_user_pod(user_id, image=image):
                await update_status(user_id, resolved_image, PodStatus.ERROR, "Failed to create pod")
                return _make_response(
                    success=False,
                    message="Failed to create pod",
                    pod_name=pod_name,
                    status=PodStatus.ERROR,
                    is_new=True,
                    image=resolved_image,
                )

            # 5. 等待 Pod 就绪（仍在 user+image 锁保护下）
            return await _wait_and_handle_ready(user_id, pod_name, resolved_image, is_new=True)

    except Exception as e:
        logfire.error(f"Error creating user pod: {e}")
        await update_status(user_id, resolved_image, PodStatus.ERROR, str(e))
        return _make_response(
            success=False,
            message=f"Internal error: {e}",
            pod_name=pod_name,
            status=PodStatus.ERROR,
            is_new=True,
            image=resolved_image,
        )


@log_span("查询用户 Pod 状态", args_captured_as_tags=["user_id", "image"])
async def get_user_pod_status(user_id: UUID | str, image: str | None = None) -> dict:
    """查询用户 Pod 状态（只读，无需锁）"""
    user_id = UUID(str(user_id)) if isinstance(user_id, str) else user_id
    resolved_image = image or ""

    # 查询数据库记录
    record = await query_record_by_user_id_and_image(user_id, resolved_image)

    # 查询 K8S Pod 状态
    k8s_status = await get_pod_status(user_id, image=image)

    # 查询生存时间
    lifetime = await query_record_lifetime(user_id, resolved_image) if record else None

    return {
        "user_id": str(user_id),
        "image": resolved_image,
        "database_record": {
            "status": record.status if record else None,
            "create_at": record.create_at.isoformat() if record else None,
            "heartbeat_at": record.heartbeat_at.isoformat() if record else None,
            "unload_at": record.unload_at.isoformat() if record and record.unload_at else None,
            "error_message": record.error_message if record else None,
        },
        "k8s_status": k8s_status,
        "lifetime_seconds": lifetime.lifetime_seconds if lifetime else None,
    }


@log_span("刷新用户 Pod 心跳", args_captured_as_tags=["user_id", "image"])
async def refresh_user_pod_heartbeat(user_id: UUID | str, image: str | None = None) -> bool:
    """刷新用户 Pod 心跳（幂等操作，无需锁）"""
    user_id = UUID(str(user_id)) if isinstance(user_id, str) else user_id
    return await update_heartbeat(user_id, image or "")


@log_span("卸载用户 Pod", args_captured_as_tags=["user_id", "image"])
@distributed_lock(lambda bound: LockNames.user_pod_schedule(
    bound.arguments['user_id'],
), timeout=300, allow_multi_lock=True)
async def unload_user_pod(user_id: UUID | str, image: str | None = None) -> bool:
    """卸载用户 Pod

    锁策略：外层 user 级锁保护 JuiceFS 资源，内层 user+image 级锁保护 Pod 操作。
    固定获取顺序 user → user+image，避免死锁。

    卸载单个 Pod 后检查该用户是否还有其他活跃 Pod。
    若无其他活跃 Pod，则自动清理 JuiceFS K8S 资源。
    """
    user_id = UUID(str(user_id)) if isinstance(user_id, str) else user_id
    resolved_image = image or ""

    # 内层 user+image 锁：保护 Pod 操作（与 execute_command 互斥）
    async with RedisDistributedLock(
        key=LockNames.user_pod_schedule_pod(user_id, resolved_image),
        timeout=300,
        allow_multi_lock=True,
    ):
        # 更新状态为 stopping
        await update_status(user_id, resolved_image, PodStatus.STOPPING)

        # 仅删除 Pod K8S 资源
        success = await delete_user_pod_only(user_id, image=image)

        if success:
            await update_status_and_unload(user_id, resolved_image, PodStatus.STOPPED)
        else:
            await update_status(user_id, resolved_image, PodStatus.ERROR, "Failed to delete pod")

    # 外层 user 锁保护下：检查该用户是否还有其他活跃 Pod
    remaining_records = await query_records_by_user_id(user_id)
    has_active = any(
        r.status in (PodStatus.RUNNING, PodStatus.CREATING)
        for r in remaining_records
    )

    if not has_active:
        logfire.info(f"用户 {user_id} 无其他活跃 Pod，清理 JuiceFS K8S 资源")
        await delete_user_k8s_resources(user_id)

    return success


@log_span("卸载用户所有 Pod（含 JuiceFS 清理）", args_captured_as_tags=["user_id"])
@distributed_lock(lambda bound: LockNames.user_pod_schedule(
    bound.arguments['user_id'],
), timeout=300)
async def unload_all_user_pods(user_id: UUID | str) -> bool:
    """卸载用户所有镜像的 Pod 并清理 JuiceFS 资源

    用于用户删除场景：删除所有 Pod + JuiceFS 资源。
    仅持有 user 级锁，内联 Pod 删除逻辑（不调用 unload_user_pod 避免自死锁）。
    """
    user_id = UUID(str(user_id)) if isinstance(user_id, str) else user_id

    # 查询用户所有记录
    records = await query_records_by_user_id(user_id)

    all_success = True
    # 逐个删除 Pod（内联逻辑，不再调用 unload_user_pod）
    for record in records:
        if record.status in (PodStatus.RUNNING, PodStatus.CREATING):
            await update_status(user_id, record.image, PodStatus.STOPPING)
            success = await delete_user_pod_only(user_id, image=record.image)
            if success:
                await update_status_and_unload(user_id, record.image, PodStatus.STOPPED)
            else:
                await update_status(user_id, record.image, PodStatus.ERROR, "Failed to delete pod")
                all_success = False

    # 删除 JuiceFS K8S 资源（Pod 已全部删除，可安全清理）
    if not await delete_user_k8s_resources(user_id):
        all_success = False

    return all_success
