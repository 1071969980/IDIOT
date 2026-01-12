"""
task_runner.py 完整实现示例

后台更新任务的主入口和流程协调。
"""

from uuid import UUID
import asyncio
import logfire
from api.redis.pubsub import publish_event


async def run_background_update_task(user_id: UUID, role_name: str) -> None:
    """
    后台更新任务的主入口函数

    执行流程:
    0. 任务启动前：发布 planning 信号（终止其他等待的任务）
    1. 第一阶段：计划更新任务（等待 30 秒）
    2. 第二阶段：准备文件内容
    3. 第三阶段：更新任务（Agent 循环）
    """
    channel = f"agent-role-update:planning:{user_id}:{role_name}"

    # ========== 0. 任务启动前：发布 planning 信号 ==========
    # 这个信号会终止所有正在第一阶段等待的旧任务
    # 实现"后来者杀死先来者"的逻辑
    await publish_event(channel)
    logfire.info("agent-role-update::task_started", user_id=str(user_id), role_name=role_name)

    try:
        # ========== 1. 第一阶段：计划更新任务 ==========
        continue_task = await execute_planning_phase(user_id, role_name)
        if not continue_task:
            logfire.info("agent-role-update::exited_by_newer_task")
            return  # 有更新的任务启动，当前任务退出

        # ========== 2. 第二阶段：准备文件内容 ==========
        preparation_result = await execute_preparation_phase(user_id, role_name)
        if preparation_result is None:
            logfire.info("agent-role-update::no_updates_pending")
            return  # 没有待处理的更新

        original_strategies, original_guidance, strategies_update_list = preparation_result

        # ========== 3. 第三阶段：更新任务 ==========
        await execute_update_phase(
            user_id=user_id,
            role_name=role_name,
            original_strategies=original_strategies,
            original_guidance=original_guidance,
            strategies_update_list=strategies_update_list
        )

        logfire.info("agent-role-update::task_completed", user_id=str(user_id), role_name=role_name)

    except Exception as e:
        logfire.error(
            "agent-role-update::task_failed",
            user_id=str(user_id),
            role_name=role_name,
            error_type=type(e).__name__,
            error_message=str(e)
        )
        # 任务失败，不重新抛出异常（后台任务不应影响主流程）
