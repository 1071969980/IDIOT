"""用户 Pod 调度器接口实现"""

from typing import Annotated, Optional
from fastapi import Body, Query

from api.user_pod_scheduler.scheduler import (
    create_or_start_user_pod,
    get_user_pod_status,
    refresh_user_pod_heartbeat,
    unload_user_pod,
)

from .data_model import (
    CreatePodRequest, CreatePodResponse,
    PodStatusResponse, HeartbeatRequest, HeartbeatResponse, UnloadPodResponse
)
from .router_declare import router


@router.post("/create", response_model=CreatePodResponse)
async def create_pod(
    request: Annotated[CreatePodRequest, Body()],
) -> CreatePodResponse:
    """创建或拉起用户 Pod

    - 检查并保证用户分布式文件系统已经初始化
    - 检查并尝试创建 K8S 资源，等待容器状态正常
    - 在 PostgreSQL 中记录容器创建信息
    """
    result = await create_or_start_user_pod(request.user_id, image=request.image)
    return CreatePodResponse(**result)


@router.get("/status/{user_id}", response_model=PodStatusResponse)
async def get_status(
    user_id: str,
    image: Optional[str] = Query(None, description="容器镜像"),
) -> PodStatusResponse:
    """查询用户 Pod 状态

    - 查询指定用户 Pod 运行状态
    - 查询 JuiceFS 挂载状态
    - 返回用户 Pod 的生存时间
    """
    result = await get_user_pod_status(user_id, image=image)
    return PodStatusResponse(**result)


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(
    request: Annotated[HeartbeatRequest, Body()],
) -> HeartbeatResponse:
    """刷新容器心跳

    刷新容器创建记录的心跳记录时间
    """
    success = await refresh_user_pod_heartbeat(request.user_id, image=request.image)
    return HeartbeatResponse(
        success=success,
        message="Heartbeat refreshed" if success else "Failed to refresh heartbeat"
    )


@router.delete("/unload/{user_id}", response_model=UnloadPodResponse)
async def unload_pod(
    user_id: str,
    image: Optional[str] = Query(None, description="容器镜像"),
) -> UnloadPodResponse:
    """手动卸载用户 Pod（仅删除 Pod，保留 JuiceFS 资源）"""
    success = await unload_user_pod(user_id, image=image)
    if success:
        return UnloadPodResponse(success=True, message="Pod unloaded successfully")
    return UnloadPodResponse(success=False, message="Failed to unload pod")
