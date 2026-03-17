"""用户文件系统目录操作端点"""

import os
from typing import Annotated

import logfire
from fastapi import Body, Depends, HTTPException, status

from api.authentication.sql_stat.utils import _User
from api.authentication.utils import get_current_active_user
from api.juiceFS.client_worker import Operation, get_worker_pool
from api.juiceFS.client_worker.exceptions import TaskExecutionError, TaskTimeoutError
from api.juiceFS.client_worker.models import ListdirEntry

from .data_model import (
    CreateDirRequest,
    CreateDirResponse,
    FileInfo,
    ListDirRequest,
    ListDirResponse,
)
from .router_declare import router
from .utils import (
    _is_dir_from_mode,
    _strip_pvc_prefix,
    get_meta_url,
    get_pvc_name,
    validate_and_build_path,
)


# ============================================================
# 列出目录
# ============================================================


@router.post("/list", response_model=ListDirResponse)
async def list_dir(
    request: Annotated[ListDirRequest, Body()],
    user: Annotated[_User, Depends(get_current_active_user)],
) -> ListDirResponse:
    """列出目录内容"""
    user_id = str(user.id)
    meta_url = get_meta_url(user_id)
    pvc_name = get_pvc_name(user_id)
    pool = get_worker_pool()

    # 构建安全路径
    safe_path = validate_and_build_path(request.path, pvc_name)

    with logfire.span("user_file_system::list_dir", path=safe_path, user_id=user_id):
        try:
            # 始终使用 detail=True 获取完整信息
            result = await pool.call(meta_url, Operation.LISTDIR, safe_path, True)
            entries = []

            for entry in result.entries:
                # detail=True 时，entry 始终是 ListdirEntry
                assert isinstance(entry, ListdirEntry)
                entry_path = _strip_pvc_prefix(
                    os.path.join(safe_path, entry.name), pvc_name
                )
                entries.append(
                    FileInfo(
                        name=entry.name,
                        path=entry_path,
                        is_dir=_is_dir_from_mode(entry.st_mode),
                        size=entry.st_size,
                        st_mode=entry.st_mode,
                        st_mtime=entry.st_mtime,
                    )
                )

            return ListDirResponse(entries=entries)

        except TaskExecutionError as e:
            if "not found" in str(e).lower() or "no such file" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"目录不存在: {request.path}",
                ) from e
            logfire.error("列出目录失败", path=safe_path, error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="列出目录失败",
            ) from e
        except TaskTimeoutError as e:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="操作超时",
            ) from e


# ============================================================
# 创建目录
# ============================================================


@router.post("/mkdir", response_model=CreateDirResponse)
async def create_dir(
    request: Annotated[CreateDirRequest, Body()],
    user: Annotated[_User, Depends(get_current_active_user)],
) -> CreateDirResponse:
    """创建目录（递归创建父目录）"""
    user_id = str(user.id)
    meta_url = get_meta_url(user_id)
    pvc_name = get_pvc_name(user_id)
    pool = get_worker_pool()

    # 构建安全路径
    safe_path = validate_and_build_path(request.path, pvc_name)

    with logfire.span("user_file_system::create_dir", path=safe_path, user_id=user_id):
        try:
            result = await pool.call(
                meta_url, Operation.MKDIRS, safe_path, 0o777, request.exist_ok
            )
            return CreateDirResponse(success=result.success, path=request.path)

        except TaskExecutionError as e:
            if "exists" in str(e).lower() and not request.exist_ok:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"目录已存在: {request.path}",
                ) from e
            logfire.error("创建目录失败", path=safe_path, error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="创建目录失败",
            ) from e
        except TaskTimeoutError as e:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="操作超时",
            ) from e