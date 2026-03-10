"""心跳检查定时任务"""

import asyncio
import logfire
from datetime import datetime, timedelta

from api.user_pod_scheduler.constants import (
    HEARTBEAT_TIMEOUT_SECONDS,
    HEARTBEAT_CHECK_INTERVAL_SECONDS,
)
from api.user_pod_scheduler.scheduler import unload_user_pod
from api.user_pod_scheduler.sql_stat.utils import query_timeout_records
from api.app.graceful_shutdown import (
    set_following_task_for_graceful_shutdown,
    set_following_task_for_graceful_shutdown_timeout,
)


async def check_and_unload_timeout_pods() -> None:
    """检查并卸载心跳超时的 Pod"""
    logfire.info("Starting heartbeat check...")

    # 计算心跳超时阈值
    threshold = datetime.now() - timedelta(seconds=HEARTBEAT_TIMEOUT_SECONDS)

    # 查询超时记录
    timeout_records = await query_timeout_records(threshold)

    if not timeout_records:
        logfire.debug("No timeout pods found")
        return

    logfire.info(f"Found {len(timeout_records)} timeout pods to unload")

    # 卸载超时的 Pod
    for record in timeout_records:
        try:
            logfire.info(f"Unloading timeout pod for user {record.user_id}")
            success = await unload_user_pod(record.user_id)
            if success:
                logfire.info(f"Successfully unloaded pod for user {record.user_id}")
            else:
                logfire.error(f"Failed to unload pod for user {record.user_id}")
        except Exception as e:
            logfire.error(f"Error unloading pod for user {record.user_id}: {e}")


async def heartbeat_checker_loop() -> None:
    """心跳检查循环"""
    logfire.info("Heartbeat checker started")

    while True:
        try:
            await check_and_unload_timeout_pods()
        except Exception as e:
            logfire.error(f"Error in heartbeat check: {e}")

        await asyncio.sleep(HEARTBEAT_CHECK_INTERVAL_SECONDS)


def start_heartbeat_checker() -> asyncio.Task:
    """启动心跳检查任务"""
    with set_following_task_for_graceful_shutdown():
        with set_following_task_for_graceful_shutdown_timeout(300):  # 5分钟超时
            task = asyncio.create_task(heartbeat_checker_loop())

    logfire.info("Heartbeat checker task created")
    return task