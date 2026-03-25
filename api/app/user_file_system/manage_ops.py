"""用户文件系统管理操作端点"""

from typing import Annotated

import logfire
from fastapi import Body, Depends, HTTPException, status

from api.authentication.sql_stat.utils import _User
from api.authentication.utils import get_current_active_user
from api.juiceFS.client_worker import Operation, get_worker_pool
from api.juiceFS.client_worker.exceptions import TaskExecutionError, TaskTimeoutError

from .data_model import (
    CopyRequest,
    CopyResponse,
    DeleteRequest,
    DeleteResponse,
    MoveRequest,
    MoveResponse,
)
from .router_declare import router
from .utils import get_meta_url, get_pvc_name, is_dir_from_mode, validate_and_build_path


# ============================================================
# 移动/重命名
# ============================================================


@router.post("/move", response_model=MoveResponse)
async def move_file(
    request: Annotated[MoveRequest, Body()],
    user: Annotated[_User, Depends(get_current_active_user)],
) -> MoveResponse:
    """移动或重命名文件/目录"""
    user_id = str(user.id)
    meta_url = get_meta_url(user_id)
    pvc_name = get_pvc_name(user_id)
    pool = get_worker_pool()

    # 构建安全路径
    safe_source = validate_and_build_path(request.source, pvc_name)
    safe_destination = validate_and_build_path(request.destination, pvc_name)

    with logfire.span(
        "user_file_system::move_file",
        source=safe_source,
        destination=safe_destination,
        user_id=user_id,
    ):
        try:
            result = await pool.call(meta_url, Operation.RENAME, safe_source, safe_destination)
            return MoveResponse(
                success=result.success,
                source=request.source,
                destination=request.destination,
            )

        except TaskExecutionError as e:
            if "not found" in str(e).lower() or "no such file" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"源路径不存在: {request.source}",
                ) from e
            logfire.error("移动失败", source=safe_source, destination=safe_destination, error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="移动失败",
            ) from e
        except TaskTimeoutError as e:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="操作超时",
            ) from e


# ============================================================
# 复制
# ============================================================


@router.post("/copy", response_model=CopyResponse)
async def copy_file(
    request: Annotated[CopyRequest, Body()],
    user: Annotated[_User, Depends(get_current_active_user)],
) -> CopyResponse:
    """克隆文件或目录"""
    user_id = str(user.id)
    meta_url = get_meta_url(user_id)
    pvc_name = get_pvc_name(user_id)
    pool = get_worker_pool()

    # 构建安全路径
    safe_source = validate_and_build_path(request.source, pvc_name)
    safe_destination = validate_and_build_path(request.destination, pvc_name)

    with logfire.span(
        "user_file_system::copy_file",
        source=safe_source,
        destination=safe_destination,
        user_id=user_id,
    ):
        try:
            # 使用 CLONE 操作克隆文件或目录
            await pool.call(meta_url, Operation.CLONE, safe_source, safe_destination)

            return CopyResponse(
                success=True,
                source=request.source,
                destination=request.destination,
            )

        except TaskExecutionError as e:
            if "not found" in str(e).lower() or "no such file" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"源路径不存在: {request.source}",
                ) from e
            logfire.error("复制失败", source=safe_source, destination=safe_destination, error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="复制失败",
            ) from e
        except TaskTimeoutError as e:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="操作超时",
            ) from e


# ============================================================
# 删除
# ============================================================


@router.post("/delete", response_model=DeleteResponse)
async def delete_file(
    request: Annotated[DeleteRequest, Body()],
    user: Annotated[_User, Depends(get_current_active_user)],
) -> DeleteResponse:
    """删除文件或目录"""
    user_id = str(user.id)
    meta_url = get_meta_url(user_id)
    pvc_name = get_pvc_name(user_id)
    pool = get_worker_pool()

    # 构建安全路径
    safe_path = validate_and_build_path(request.path, pvc_name)

    with logfire.span("user_file_system::delete_file", path=safe_path, user_id=user_id):
        try:
            # 先检查路径是否存在并获取状态
            exists_result = await pool.call(meta_url, Operation.EXISTS, safe_path)
            if not exists_result.exists:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"路径不存在: {request.path}",
                )

            # 获取状态以判断是文件还是目录
            stat_result = await pool.call(meta_url, Operation.STAT, safe_path)
            is_dir = is_dir_from_mode(stat_result.stat_info.st_mode)

            if is_dir:
                if request.recursive:
                    # 使用 RMR 操作递归删除目录
                    await pool.call(meta_url, Operation.RMR, safe_path)
                else:
                    # 非递归删除，尝试删除空目录
                    result = await pool.call(meta_url, Operation.RMDIR, safe_path)
                    if not result.success:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"目录非空，需要递归删除: {request.path}",
                        )
            else:
                # 删除文件
                await pool.call(meta_url, Operation.REMOVE, safe_path)

            return DeleteResponse(success=True, path=request.path)

        except HTTPException:
            raise
        except TaskExecutionError as e:
            logfire.error("删除失败", path=safe_path, error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="删除失败",
            ) from e
        except TaskTimeoutError as e:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="操作超时",
            ) from e