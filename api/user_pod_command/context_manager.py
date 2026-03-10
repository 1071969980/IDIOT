"""用户 Pod 命令会话上下文管理器"""

import asyncio
import time
import logfire
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from uuid import UUID

from api.juiceFS.string_utils import get_string_var, StringVarName
from api.user_pod_scheduler.constants import K8S_NAMESPACE, PodStatus

from .constants import (
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_STATUS_CHECK_INTERVAL_SECONDS,
    DEFAULT_SESSION_TIMEOUT_SECONDS,
    DEFAULT_POD_READY_TIMEOUT_SECONDS,
)
from .exceptions import (
    PodNotReadyError,
    PodCreationTimeoutError,
    PodStatusAbnormalError,
)
from .data_model import PodCommandSession
from .scheduler_client import SchedulerClient, get_scheduler_client


@asynccontextmanager
async def pod_command_session(
    user_id: UUID | str,
    heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    status_check_interval: float = DEFAULT_STATUS_CHECK_INTERVAL_SECONDS,
    session_timeout: float = DEFAULT_SESSION_TIMEOUT_SECONDS,
    pod_ready_timeout: float = DEFAULT_POD_READY_TIMEOUT_SECONDS,
) -> AsyncGenerator[PodCommandSession, None]:
    """
    Pod 命令会话上下文管理器。

    进入时：
    1. 查询容器状态，不存在则拉起
    2. 等待 Pod 就绪，超时抛出异常
    3. 初始化多线程信号 Event
    4. 启动心跳循环任务
    5. 启动状态监测任务
    6. 启动超时计时任务

    退出时：
    1. 终止所有管理任务

    Args:
        user_id: 用户ID
        heartbeat_interval: 心跳间隔（秒）
        status_check_interval: 状态检查间隔（秒）
        session_timeout: 会话超时时间（秒）
        pod_ready_timeout: Pod 就绪等待超时（秒）

    Yields:
        PodCommandSession: 会话对象，包含 interrupt_event

    Raises:
        PodCreationTimeoutError: Pod 创建超时
        PodNotReadyError: Pod 未就绪
        PodStatusAbnormalError: Pod 状态异常
    """
    user_id = UUID(str(user_id)) if isinstance(user_id, str) else user_id
    scheduler_client = get_scheduler_client()

    # 1. 查询/创建 Pod
    with logfire.span("初始化 Pod 命令会话", user_id=str(user_id)):
        status_result = await scheduler_client.get_pod_status(user_id)

        if not status_result.k8s_status.get("exists"):
            logfire.info(f"Pod 不存在，正在创建: {user_id}")
            create_result = await scheduler_client.create_pod(user_id)
            if not create_result.success:
                raise PodNotReadyError(f"Failed to create pod: {create_result.message}")

        # 2. 等待 Pod 就绪
        await _wait_for_pod_ready(user_id, scheduler_client, pod_ready_timeout)

    # 3. 初始化会话对象
    pod_name = get_string_var(StringVarName.K8S_User_POD_Name, user_id)
    session = PodCommandSession(
        user_id=user_id,
        pod_name=pod_name,
        namespace=K8S_NAMESPACE,
    )

    # 后台任务列表
    tasks: list[asyncio.Task] = []

    try:
        # 4. 启动心跳循环任务
        heartbeat_task = asyncio.create_task(
            _heartbeat_loop(user_id, scheduler_client, heartbeat_interval, session)
        )
        tasks.append(heartbeat_task)

        # 5. 启动状态监测任务
        status_task = asyncio.create_task(
            _status_monitor_loop(user_id, scheduler_client, status_check_interval, session)
        )
        tasks.append(status_task)

        # 6. 启动超时计时任务
        timeout_task = asyncio.create_task(
            _timeout_watcher(session_timeout, session)
        )
        tasks.append(timeout_task)

        logfire.info(f"Pod 命令会话已建立: user_id={user_id}, pod={pod_name}")
        yield session

    finally:
        # 退出时终止所有任务
        session.is_active = False
        for task in tasks:
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        logfire.info(f"Pod 命令会话已关闭: user_id={user_id}")


async def _wait_for_pod_ready(
    user_id: UUID,
    scheduler_client: SchedulerClient,
    timeout: float
) -> None:
    """等待 Pod 就绪"""
    start_time = time.time()

    while True:
        elapsed = time.time() - start_time
        if elapsed > timeout:
            raise PodCreationTimeoutError(f"Pod creation timeout after {timeout}s")

        status_result = await scheduler_client.get_pod_status(user_id)
        k8s_status = status_result.k8s_status

        if k8s_status.get("exists") and k8s_status.get("phase") == "Running":
            return

        db_status = status_result.database_record.get("status")
        if db_status == PodStatus.ERROR:
            error_msg = status_result.database_record.get("error_message", "Unknown error")
            raise PodStatusAbnormalError(f"Pod in error state: {error_msg}")

        await asyncio.sleep(2)


async def _heartbeat_loop(
    user_id: UUID,
    scheduler_client: SchedulerClient,
    interval: float,
    session: PodCommandSession
) -> None:
    """心跳循环任务"""
    while session.is_active:
        try:
            response = await scheduler_client.send_heartbeat(user_id)
            if response.success:
                logfire.debug(f"Heartbeat refreshed: {user_id}")
            else:
                logfire.warning(f"Heartbeat failed: {user_id} - {response.message}")
        except Exception as e:
            logfire.error(f"Heartbeat error: {e}")

        # 分段等待，以便响应取消
        for _ in range(int(interval)):
            if not session.is_active:
                return
            await asyncio.sleep(1)
        # 处理小数部分
        if interval % 1 > 0 and session.is_active:
            await asyncio.sleep(interval % 1)


async def _status_monitor_loop(
    user_id: UUID,
    scheduler_client: SchedulerClient,
    interval: float,
    session: PodCommandSession
) -> None:
    """状态监测任务"""
    while session.is_active:
        try:
            status_result = await scheduler_client.get_pod_status(user_id)
            k8s_status = status_result.k8s_status

            if not k8s_status.get("exists") or k8s_status.get("phase") != "Running":
                logfire.warning(f"Pod status abnormal: {k8s_status}")
                session.last_error = f"Pod status abnormal: {k8s_status.get('phase')}"
                session.interrupt_event.set()
                session.is_active = False
                break

        except Exception as e:
            logfire.error(f"Status check failed: {e}")

        # 分段等待，以便响应取消
        for _ in range(int(interval)):
            if not session.is_active:
                return
            await asyncio.sleep(1)
        if interval % 1 > 0 and session.is_active:
            await asyncio.sleep(interval % 1)


async def _timeout_watcher(
    timeout: float,
    session: PodCommandSession
) -> None:
    """超时计时任务"""
    await asyncio.sleep(timeout)

    if session.is_active:
        logfire.warning(f"Session timeout: {session.user_id}")
        session.last_error = f"Session timeout after {timeout}s"
        session.interrupt_event.set()
        session.is_active = False