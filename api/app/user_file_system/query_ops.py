"""用户文件系统查询操作端点"""

from typing import Annotated

import logfire
from fastapi import Body, Depends, HTTPException, status

from api.authentication.sql_stat.utils import _User
from api.authentication.utils import get_current_active_user
from api.juiceFS.client_worker import Operation, get_worker_pool
from api.juiceFS.client_worker.exceptions import TaskExecutionError, TaskTimeoutError

from .data_model import ExistsRequest, ExistsResponse, StatRequest, StatResponse
from .router_declare import router
from .utils import get_meta_url, get_pvc_name, is_dir_from_mode, validate_and_build_path


# ============================================================
# 检查存在
# ============================================================


@router.post("/exists", response_model=ExistsResponse)
async def check_exists(
    request: Annotated[ExistsRequest, Body()],
    user: Annotated[_User, Depends(get_current_active_user)],
) -> ExistsResponse:
    """检查路径是否存在"""
    user_id = str(user.id)
    meta_url = get_meta_url(user_id)
    pvc_name = get_pvc_name(user_id)
    pool = get_worker_pool()

    # 构建安全路径
    safe_path = validate_and_build_path(request.path, pvc_name)

    with logfire.span("user_file_system::check_exists", path=safe_path, user_id=user_id):
        try:
            exists_result = await pool.call(meta_url, Operation.EXISTS, safe_path)

            if not exists_result.exists:
                return ExistsResponse(exists=False, path=request.path)

            # 获取状态以判断是否为目录
            stat_result = await pool.call(meta_url, Operation.STAT, safe_path)
            is_dir = is_dir_from_mode(stat_result.stat_info.st_mode)

            return ExistsResponse(
                exists=True,
                is_dir=is_dir,
                path=request.path,
            )

        except TaskExecutionError as e:
            # EXISTS 操作不应该抛出 "not found" 错误，但以防万一
            if "not found" in str(e).lower():
                return ExistsResponse(exists=False, path=request.path)
            logfire.error("检查存在失败", path=safe_path, error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="检查存在失败",
            ) from e
        except TaskTimeoutError as e:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="操作超时",
            ) from e


# ============================================================
# 获取状态
# ============================================================


@router.post("/stat", response_model=StatResponse)
async def get_stat(
    request: Annotated[StatRequest, Body()],
    user: Annotated[_User, Depends(get_current_active_user)],
) -> StatResponse:
    """获取文件/目录状态信息"""
    user_id = str(user.id)
    meta_url = get_meta_url(user_id)
    pvc_name = get_pvc_name(user_id)
    pool = get_worker_pool()

    # 构建安全路径
    safe_path = validate_and_build_path(request.path, pvc_name)

    with logfire.span("user_file_system::get_stat", path=safe_path, user_id=user_id):
        try:
            result = await pool.call(meta_url, Operation.STAT, safe_path)
            stat_info = result.stat_info

            return StatResponse(
                name=stat_info.name,
                path=request.path,
                is_dir=is_dir_from_mode(stat_info.st_mode),
                st_mode=stat_info.st_mode,
                st_ino=stat_info.st_ino,
                st_dev=stat_info.st_dev,
                st_nlink=stat_info.st_nlink,
                st_uid=stat_info.st_uid,
                st_gid=stat_info.st_gid,
                st_size=stat_info.st_size,
                st_atime=stat_info.st_atime,
                st_mtime=stat_info.st_mtime,
                st_ctime=stat_info.st_ctime,
            )

        except TaskExecutionError as e:
            if "not found" in str(e).lower() or "no such file" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"路径不存在: {request.path}",
                ) from e
            logfire.error("获取状态失败", path=safe_path, error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="获取状态失败",
            ) from e
        except TaskTimeoutError as e:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="操作超时",
            ) from e