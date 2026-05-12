"""用户项目操作端点"""

from pathlib import PurePosixPath
from typing import Annotated

import logfire
from fastapi import Body, Depends, HTTPException, status

from api.authentication.sql_stat.utils import _User
from api.authentication.utils import get_current_active_user
from api.juiceFS.client_worker import Operation, get_worker_pool
from api.juiceFS.client_worker.exceptions import TaskExecutionError, TaskTimeoutError
from api.user_pod_command import (
    pod_command_session,
    execute_command,
    PodCreationTimeoutError,
    PodStatusAbnormalError,
    UserPodCommandError,
)
from api.user_pod_scheduler.constants import JUICEFS_MOUNT_PATH

from ..router_declare import router
from ..utils import get_meta_url, get_pvc_name, validate_and_build_path
from .data_model import (
    CreateProjectRequest,
    CreateProjectResponse,
    CreateProjectMemoryRequest,
    CreateProjectMemoryResponse,
    DeleteProjectRequest,
    DeleteProjectResponse,
    ProjectExistsRequest,
    ProjectExistsResponse,
)


def _build_project_paths(
    project_path: str, pvc_name: str
) -> tuple[str, str, str, str]:
    """构建项目相关的 SDK 路径和容器内路径

    Args:
        project_path: 用户输入的项目相对路径
        pvc_name: 用户的 PVC 名称

    Returns:
        (sdk_project_path, container_project_path, sdk_memory_path, container_memory_path)
    """
    normalized = PurePosixPath(project_path.strip())

    pub_project_rel = str(PurePosixPath("pub") / normalized)
    memory_project_rel = str(
        PurePosixPath("sys") / "memory" / "projects" / normalized
    )

    sdk_project_path = validate_and_build_path(pub_project_rel, pvc_name)
    sdk_memory_path = validate_and_build_path(memory_project_rel, pvc_name)

    mount = PurePosixPath(JUICEFS_MOUNT_PATH)
    container_project_path = str(mount / "pub" / normalized)
    container_memory_path = str(mount / "sys" / "memory" / "projects" / normalized)

    return sdk_project_path, container_project_path, sdk_memory_path, container_memory_path


async def _git_init_in_container(user_id: str, container_path: str) -> None:
    """在用户容器内执行 git init

    Args:
        user_id: 用户 ID
        container_path: 容器内的目标路径

    Raises:
        HTTPException: 容器不可用或 git init 失败
    """
    try:
        async with pod_command_session(user_id=user_id) as session:
            result = await execute_command(
                pod_command_session_struct=session,
                command=f"git init {container_path}",
                timeout=60,
            )
    except PodCreationTimeoutError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"容器创建超时: {e}",
        ) from e
    except PodStatusAbnormalError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"容器状态异常: {e}",
        ) from e
    except UserPodCommandError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"容器命令执行错误: {e}",
        ) from e

    if result.returncode != 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"git init 失败: {result.stderr}",
        )


# ============================================================
# 创建项目
# ============================================================


@router.post("/project/create", response_model=CreateProjectResponse)
async def create_project(
    request: Annotated[CreateProjectRequest, Body()],
    user: Annotated[_User, Depends(get_current_active_user)],
) -> CreateProjectResponse:
    """创建用户项目，可选开启记忆功能"""
    user_id = str(user.id)
    meta_url = get_meta_url(user_id)
    pvc_name = get_pvc_name(user_id)
    pool = get_worker_pool()

    sdk_project, container_project, sdk_memory, container_memory = (
        _build_project_paths(request.project_path, pvc_name)
    )

    with logfire.span(
        "user_file_system::create_project",
        project_path=request.project_path,
        user_id=user_id,
    ):
        try:
            # 1. 检查项目是否已存在
            exists = await pool.call(meta_url, Operation.EXISTS, sdk_project)
            if exists:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"项目已存在: {request.project_path}",
                )

            # 2. 创建项目目录
            await pool.call(meta_url, Operation.MKDIRS, sdk_project, 0o777, False)

        except TaskExecutionError as e:
            if "exists" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"项目已存在: {request.project_path}",
                ) from e
            logfire.error("创建项目目录失败", path=sdk_project, error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="创建项目目录失败",
            ) from e
        except TaskTimeoutError as e:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="操作超时",
            ) from e

        # 3. 在容器内 git init
        await _git_init_in_container(user_id, container_project)

        # 4. 可选：创建记忆目录
        memory_enabled = False
        if request.enable_memory:
            try:
                await pool.call(meta_url, Operation.MKDIRS, sdk_memory, 0o777, False)
                await _git_init_in_container(user_id, container_memory)
                memory_enabled = True
            except TaskExecutionError as e:
                logfire.error("创建记忆目录失败", path=sdk_memory, error=str(e))
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="创建记忆目录失败",
                ) from e
            except TaskTimeoutError as e:
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail="操作超时",
                ) from e

    return CreateProjectResponse(
        success=True,
        project_path=request.project_path,
        memory_enabled=memory_enabled,
    )


# ============================================================
# 查询项目是否存在
# ============================================================


@router.post("/project/exists", response_model=ProjectExistsResponse)
async def project_exists(
    request: Annotated[ProjectExistsRequest, Body()],
    user: Annotated[_User, Depends(get_current_active_user)],
) -> ProjectExistsResponse:
    """查询指定项目是否存在"""
    user_id = str(user.id)
    meta_url = get_meta_url(user_id)
    pvc_name = get_pvc_name(user_id)
    pool = get_worker_pool()

    sdk_project, _, _, _ = _build_project_paths(request.project_path, pvc_name)

    with logfire.span(
        "user_file_system::project_exists",
        project_path=request.project_path,
        user_id=user_id,
    ):
        try:
            exists = await pool.call(meta_url, Operation.EXISTS, sdk_project)
        except TaskExecutionError as e:
            logfire.error("查询项目失败", path=sdk_project, error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="查询项目失败",
            ) from e
        except TaskTimeoutError as e:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="操作超时",
            ) from e

    return ProjectExistsResponse(
        exists=bool(exists),
        project_path=request.project_path,
    )


# ============================================================
# 删除项目
# ============================================================


@router.post("/project/delete", response_model=DeleteProjectResponse)
async def delete_project(
    request: Annotated[DeleteProjectRequest, Body()],
    user: Annotated[_User, Depends(get_current_active_user)],
) -> DeleteProjectResponse:
    """删除用户项目及其记忆文件夹"""
    user_id = str(user.id)
    meta_url = get_meta_url(user_id)
    pvc_name = get_pvc_name(user_id)
    pool = get_worker_pool()

    sdk_project, _, sdk_memory, _ = _build_project_paths(
        request.project_path, pvc_name
    )

    with logfire.span(
        "user_file_system::delete_project",
        project_path=request.project_path,
        user_id=user_id,
    ):
        try:
            # 删除项目目录
            await pool.call(meta_url, Operation.RMR, sdk_project)

            # 尝试删除记忆目录（如果存在）
            memory_exists = await pool.call(
                meta_url, Operation.EXISTS, sdk_memory
            )
            if memory_exists:
                await pool.call(meta_url, Operation.RMR, sdk_memory)

        except TaskExecutionError as e:
            logfire.error("删除项目失败", path=sdk_project, error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="删除项目失败",
            ) from e
        except TaskTimeoutError as e:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="操作超时",
            ) from e

    return DeleteProjectResponse(
        success=True,
        project_path=request.project_path,
    )


# ============================================================
# 独立创建项目记忆文件夹
# ============================================================


@router.post("/project/create_memory", response_model=CreateProjectMemoryResponse)
async def create_project_memory(
    request: Annotated[CreateProjectMemoryRequest, Body()],
    user: Annotated[_User, Depends(get_current_active_user)],
) -> CreateProjectMemoryResponse:
    """为已有项目创建记忆文件夹"""
    user_id = str(user.id)
    meta_url = get_meta_url(user_id)
    pvc_name = get_pvc_name(user_id)
    pool = get_worker_pool()

    sdk_project, _, sdk_memory, container_memory = _build_project_paths(
        request.project_path, pvc_name
    )

    with logfire.span(
        "user_file_system::create_project_memory",
        project_path=request.project_path,
        user_id=user_id,
    ):
        try:
            # 1. 检查项目是否存在
            project_exists = await pool.call(
                meta_url, Operation.EXISTS, sdk_project
            )
            if not project_exists:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"项目不存在: {request.project_path}",
                )

            # 2. 检查记忆目录是否已存在
            memory_exists = await pool.call(
                meta_url, Operation.EXISTS, sdk_memory
            )
            if memory_exists:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"项目记忆文件夹已存在: {request.project_path}",
                )

            # 3. 创建记忆目录
            await pool.call(meta_url, Operation.MKDIRS, sdk_memory, 0o777, False)

        except TaskExecutionError as e:
            logfire.error("创建记忆目录失败", path=sdk_memory, error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="创建记忆目录失败",
            ) from e
        except TaskTimeoutError as e:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="操作超时",
            ) from e

        # 4. 在容器内 git init
        await _git_init_in_container(user_id, container_memory)

    return CreateProjectMemoryResponse(
        success=True,
        project_path=request.project_path,
    )
