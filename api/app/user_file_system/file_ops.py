"""用户文件系统文件操作端点"""

import os
import urllib.parse
from typing import Annotated

import logfire
from fastapi import Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from api.authentication.sql_stat.utils import _User
from api.authentication.utils import get_current_active_user
from api.juiceFS.client_worker import Operation, get_worker_pool
from api.juiceFS.client_worker.exceptions import TaskExecutionError, TaskTimeoutError

from .data_model import DownloadRequest, UploadResponse
from .router_declare import router
from .utils import get_meta_url, get_pvc_name, validate_and_build_path


# ============================================================
# 下载文件
# ============================================================


@router.post("/download")
async def download_file(
    request: DownloadRequest,
    user: Annotated[_User, Depends(get_current_active_user)],
) -> StreamingResponse:
    """下载文件（流式响应）"""
    path = request.path
    user_id = str(user.id)
    meta_url = get_meta_url(user_id)
    pvc_name = get_pvc_name(user_id)
    pool = get_worker_pool()

    # 构建安全路径
    safe_path = validate_and_build_path(path, pvc_name)

    with logfire.span("user_file_system::download_file", path=safe_path, user_id=user_id):
        try:
            result = await pool.call(meta_url, Operation.READ, safe_path)

            async def iter_content():
                yield result.content

            filename = os.path.basename(safe_path)
            # RFC 5987 编码，支持中文文件名
            encoded_filename = urllib.parse.quote(filename, safe="")
            return StreamingResponse(
                iter_content(),
                media_type="application/octet-stream",
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
                },
            )

        except TaskExecutionError as e:
            if "not found" in str(e).lower() or "no such file" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"文件不存在: {path}",
                ) from e
            logfire.error("下载文件失败", path=safe_path, error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="下载文件失败",
            ) from e
        except TaskTimeoutError as e:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="操作超时",
            ) from e


# ============================================================
# 上传文件
# ============================================================


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    path: Annotated[str, Query(description="目标文件路径")],
    file: UploadFile,
    user: Annotated[_User, Depends(get_current_active_user)],
) -> UploadResponse:
    """上传文件"""
    user_id = str(user.id)
    meta_url = get_meta_url(user_id)
    pvc_name = get_pvc_name(user_id)
    pool = get_worker_pool()

    # 构建安全路径
    safe_path = validate_and_build_path(path, pvc_name)

    with logfire.span("user_file_system::upload_file", path=safe_path, user_id=user_id):
        try:
            content = await file.read()
            result = await pool.call(meta_url, Operation.WRITE, safe_path, content)
            return UploadResponse(
                success=True,
                path=path,
                bytes_written=result.bytes_written,
            )

        except TaskExecutionError as e:
            logfire.error("上传文件失败", path=safe_path, error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="上传文件失败",
            ) from e
        except TaskTimeoutError as e:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="操作超时",
            ) from e