from typing import Annotated

from fastapi import Body

from api.juiceFS.creator import (
    check_juicefs_formatted,
    create_juicefs_filesystem,
    create_minio_bucket,
    create_postgresql_database,
)

from .data_model import CreateJuiceFSRequest, CreateJuiceFSResponse
from .router_declare import router


@router.post("/test/minio-bucket", response_model=CreateJuiceFSResponse)
async def test_create_minio_bucket(
    request: Annotated[CreateJuiceFSRequest, Body()],
) -> CreateJuiceFSResponse:
    """测试创建 MinIO 存储桶"""
    success = await create_minio_bucket(request.user_id)
    return CreateJuiceFSResponse(
        success=success,
        message=f"MinIO bucket {'created' if success else 'failed to create'}",
    )


@router.post("/test/postgresql-database", response_model=CreateJuiceFSResponse)
async def test_create_postgresql_database(
    request: Annotated[CreateJuiceFSRequest, Body()],
) -> CreateJuiceFSResponse:
    """测试创建 PostgreSQL 数据库"""
    success = await create_postgresql_database(request.user_id)
    return CreateJuiceFSResponse(
        success=success,
        message=f"PostgreSQL database {'created' if success else 'failed to create'}",
    )


@router.post("/test/juicefs-filesystem", response_model=CreateJuiceFSResponse)
async def test_create_juicefs_filesystem(
    request: Annotated[CreateJuiceFSRequest, Body()],
) -> CreateJuiceFSResponse:
    """测试创建 JuiceFS 文件系统"""
    success = create_juicefs_filesystem(request.user_id)
    return CreateJuiceFSResponse(
        success=success,
        message=f"JuiceFS filesystem {'created' if success else 'failed to create'}",
    )


@router.post("/test/full-setup", response_model=CreateJuiceFSResponse)
async def test_full_juicefs_setup(
    request: Annotated[CreateJuiceFSRequest, Body()],
) -> CreateJuiceFSResponse:
    """测试完整的 JuiceFS 环境创建"""
    from api.juiceFS.creator import create_juicefs_for_user

    success = await create_juicefs_for_user(request.user_id)
    return CreateJuiceFSResponse(
        success=success,
        message=f"JuiceFS environment {'created' if success else 'failed to create'}",
    )


@router.post("/test/check-formatted", response_model=CreateJuiceFSResponse)
async def test_check_juicefs_formatted(
    request: Annotated[CreateJuiceFSRequest, Body()],
) -> CreateJuiceFSResponse:
    """测试检查 JuiceFS 是否已格式化"""
    formatted = await check_juicefs_formatted(request.user_id)
    return CreateJuiceFSResponse(
        success=formatted,
        message=f"JuiceFS {'is formatted' if formatted else 'is not formatted'}",
    )