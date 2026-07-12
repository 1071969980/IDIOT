"""命令执行工具"""

import asyncio
import time
from contextlib import suppress
from typing import Optional, Callable, Awaitable

import logfire
from kubernetes.stream import stream

from api.redis import distributed_lock
from api.redis.lock_names import LockNames
from api.user_pod_scheduler.k8s_client import get_k8s_client
from api.logger.logger import log_span

from .constants import (
    COMMAND_POLL_INTERVAL_SECONDS,
    STDOUT_CHANNEL,
    STDERR_CHANNEL,
    INTERRUPT_SIGINT,
)
from .data_model import CommandResult, PodCommandSession


@log_span("执行 Pod 命令", args_captured_as_tags=["command"])
@distributed_lock(lambda bound: LockNames.user_pod_schedule_pod(
    bound.arguments['pod_command_session_struct'].user_id,
    bound.arguments['pod_command_session_struct'].image,
), timeout=300)
async def execute_command(
    pod_command_session_struct: PodCommandSession,
    command: str,
    timeout: Optional[float] = None,
    cancel_event: asyncio.Event | None = None,
) -> CommandResult:
    """
    执行命令并返回所有输出。

    Args:
        session: Pod 命令会话
        command: 要执行的命令字符串
        timeout: 命令超时时间（秒）
        cancel_event: 取消事件，设置后立即中断命令执行并发送 SIGINT

    Returns:
        CommandResult: 包含 stdout、stderr、returncode 等信息
    """
    client = get_k8s_client()

    ws_client = None
    stdout_buffer = []
    stderr_buffer = []
    returncode = None
    interrupted = False
    error = None

    try:
        ws_client = await asyncio.to_thread(
            stream,
            client.v1.connect_get_namespaced_pod_exec,
            name=pod_command_session_struct.pod_name,
            namespace=pod_command_session_struct.namespace,
            command=["/bin/sh", "-c", command],
            stderr=True,
            stdin=True,  # 启用 stdin 以支持中断
            stdout=True,
            tty=False,
            _preload_content=False,
        )

        start_time = time.time()

        while ws_client.is_open() and pod_command_session_struct.is_active and not pod_command_session_struct.interrupt_event.is_set():
            # 超时检查
            if timeout and (time.time() - start_time) > timeout:
                error = "Command timeout"
                break

            # 轮询等待
            if cancel_event is not None:
                ws_task = asyncio.create_task(
                    asyncio.to_thread(ws_client.update, timeout=COMMAND_POLL_INTERVAL_SECONDS)
                )
                cancel_task = asyncio.create_task(cancel_event.wait())
                _done, pending = await asyncio.wait(
                    [ws_task, cancel_task], return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
                if cancel_event.is_set():
                    pod_command_session_struct.interrupt_event.set()
                    break
            else:
                await asyncio.to_thread(ws_client.update, timeout=COMMAND_POLL_INTERVAL_SECONDS)

            # 读取 stdout
            stdout_data = ws_client.read_channel(STDOUT_CHANNEL, timeout=0)
            if stdout_data:
                stdout_buffer.append(stdout_data)

            # 读取 stderr
            stderr_data = ws_client.read_channel(STDERR_CHANNEL, timeout=0)
            if stderr_data:
                stderr_buffer.append(stderr_data)

        # 检查中断原因
        if pod_command_session_struct.interrupt_event.is_set() or not pod_command_session_struct.is_active:
            interrupted = True
            error = "Command interrupted"
            # 发送中断信号
            try:
                await asyncio.to_thread(ws_client.write_stdin, INTERRUPT_SIGINT)
            except Exception:
                pass
        elif ws_client.is_open():
            # 超时退出
            pass
        else:
            # 正常结束
            returncode = ws_client.returncode

    except Exception as e:
        logfire.error(f"Command execution error: {e}")
        error = str(e)
    finally:
        if ws_client is not None:
            await asyncio.to_thread(ws_client.close)

    return CommandResult(
        stdout="".join(stdout_buffer),
        stderr="".join(stderr_buffer),
        returncode=returncode,
        interrupted=interrupted,
        error=error,
    )


@log_span("执行 Pod 命令（带回调）", args_captured_as_tags=["command"])
@distributed_lock(lambda bound: LockNames.user_pod_schedule_pod(
    bound.arguments['pod_command_session'].user_id,
    bound.arguments['pod_command_session'].image,
), timeout=300)
async def execute_command_with_callback(
    pod_command_session: PodCommandSession,
    command: str,
    on_stdout: Callable[[str], Awaitable[None]],
    on_stderr: Optional[Callable[[str], Awaitable[None]]] = None,
    timeout: Optional[float] = None,
) -> CommandResult:
    """
    执行命令并通过回调实时输出。

    Args:
        session: Pod 命令会话
        command: 要执行的命令字符串
        on_stdout: stdout 异步回调函数
        on_stderr: stderr 异步回调函数（可选）
        timeout: 命令超时时间（秒）

    Returns:
        CommandResult: 包含完整输出信息
    """
    client = get_k8s_client()

    ws_client = None
    stdout_buffer = []
    stderr_buffer = []
    returncode = None
    interrupted = False
    error = None

    try:
        ws_client = await asyncio.to_thread(
            stream,
            client.v1.connect_get_namespaced_pod_exec,
            name=pod_command_session.pod_name,
            namespace=pod_command_session.namespace,
            command=["/bin/bash", "-c", command],
            stderr=True,
            stdin=True,
            stdout=True,
            tty=False,
            _preload_content=False,
        )

        start_time = time.time()

        while ws_client.is_open() and pod_command_session.is_active and not pod_command_session.interrupt_event.is_set():
            # 超时检查
            if timeout and (time.time() - start_time) > timeout:
                error = "Command timeout"
                break

            # 短超时轮询
            await asyncio.to_thread(ws_client.update, timeout=COMMAND_POLL_INTERVAL_SECONDS)

            # 读取并回调 stdout
            stdout_data = ws_client.read_channel(STDOUT_CHANNEL, timeout=0)
            if stdout_data:
                stdout_buffer.append(stdout_data)
                await on_stdout(stdout_data)

            # 读取并回调 stderr
            stderr_data = ws_client.read_channel(STDERR_CHANNEL, timeout=0)
            if stderr_data:
                stderr_buffer.append(stderr_data)
                if on_stderr:
                    await on_stderr(stderr_data)

        # 检查中断原因
        if pod_command_session.interrupt_event.is_set() or not pod_command_session.is_active:
            interrupted = True
            error = "Command interrupted"
            # 发送中断信号
            try:
                await asyncio.to_thread(ws_client.write_stdin, INTERRUPT_SIGINT)
            except Exception:
                pass
        elif ws_client.is_open():
            # 超时退出
            pass
        else:
            # 正常结束
            returncode = ws_client.returncode

    except Exception as e:
        logfire.error(f"Command execution error: {e}")
        error = str(e)
    finally:
        if ws_client is not None:
            await asyncio.to_thread(ws_client.close)

    return CommandResult(
        stdout="".join(stdout_buffer),
        stderr="".join(stderr_buffer),
        returncode=returncode,
        interrupted=interrupted,
        error=error,
    )