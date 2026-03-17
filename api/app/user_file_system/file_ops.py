"""用户文件系统文件操作端点"""

import os
from typing import Annotated

import logfire
from fastapi import Body, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from api.authentication.sql_stat.utils import _User
from api.authentication.utils import get_current_active_user
from api.juiceFS.client_worker import Operation, get_worker_pool
from api.juiceFS.client_worker.exceptions import TaskExecutionError, TaskTimeoutError

from .data_model import (
    ReadFileRequest,
    ReadFileResponse,
    UploadResponse,
    WriteFileRequest,
    WriteFileResponse,
)
from .router_declare import router
from .utils import get_meta_url, get_pvc_name, validate_and_build_path


# ============================================================
# 创建文件
# ============================================================


@router.post("/create_file", response_model=WriteFileResponse)
async def create_file(
    request: Annotated[WriteFileRequest, Body()],
    user: Annotated[_User, Depends(get_current_active_user)],
) -> WriteFileResponse:
    """创建文件并写入内容"""
    return await _write_file(request, user)


# ============================================================
# 写入文件
# ============================================================


@router.post("/write", response_model=WriteFileResponse)
async def write_file(
    request: Annotated[WriteFileRequest, Body()],
    user: Annotated[_User, Depends(get_current_active_user)],
) -> WriteFileResponse:
    """写入文件内容"""
    return await _write_file(request, user)


async def _write_file(request: WriteFileRequest, user: _User) -> WriteFileResponse:
    """写入文件的内部实现"""
    user_id = str(user.id)
    meta_url = get_meta_url(user_id)
    pvc_name = get_pvc_name(user_id)
    pool = get_worker_pool()

    # 构建安全路径
    safe_path = validate_and_build_path(request.path, pvc_name)

    with logfire.span("user_file_system::write_file", path=safe_path, user_id=user_id):
        try:
            result = await pool.call(meta_url, Operation.WRITE, safe_path, request.content)
            return WriteFileResponse(
                success=True,
                bytes_written=result.bytes_written,
                path=request.path,
            )

        except TaskExecutionError as e:
            logfire.error("写入文件失败", path=safe_path, error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="写入文件失败",
            ) from e
        except TaskTimeoutError as e:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="操作超时",
            ) from e


# ============================================================
# 读取文件
# ============================================================


@router.post("/read", response_model=ReadFileResponse)
async def read_file(
    request: Annotated[ReadFileRequest, Body()],
    user: Annotated[_User, Depends(get_current_active_user)],
) -> ReadFileResponse:
    """读取文件内容"""
    user_id = str(user.id)
    meta_url = get_meta_url(user_id)
    pvc_name = get_pvc_name(user_id)
    pool = get_worker_pool()

    # 构建安全路径
    safe_path = validate_and_build_path(request.path, pvc_name)

    with logfire.span("user_file_system::read_file", path=safe_path, user_id=user_id):
        try:
            result = await pool.call(meta_url, Operation.READ, safe_path)
            return ReadFileResponse(content=result.content, path=request.path)

        except TaskExecutionError as e:
            if "not found" in str(e).lower() or "no such file" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"文件不存在: {request.path}",
                ) from e
            if "is a directory" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"路径是目录，不是文件: {request.path}",
                ) from e
            logfire.error("读取文件失败", path=safe_path, error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="读取文件失败",
            ) from e
        except TaskTimeoutError as e:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="操作超时",
            ) from e


# ============================================================
# 下载文件
# ============================================================


@router.get("/download")
async def download_file(
    path: Annotated[str, Query(description="文件路径")],
    user: Annotated[_User, Depends(get_current_active_user)],
) -> StreamingResponse:
    """下载文件（流式响应）"""
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
            return StreamingResponse(
                iter_content(),
                media_type="application/octet-stream",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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