"""
第一阶段：计划更新任务

功能：防止多个任务同时进入第一阶段（后来者杀死先来者）

执行逻辑：
1. 任务启动前，task_runner 会发布 planning 信号
2. 本函数订阅 Redis 频道并等待 30 秒超时
3. 如果收到新的 planning 信号 → 有新任务来抢占，返回 False（退出任务）
4. 如果超时 → 没有新任务来抢占，返回 True（继续执行第二阶段）

设计文档参考：
- api/agent/tools/agent_roles/update_role_conversation_strategies/background_update_task_spec_docs/background_update_task_spec_design.md#21-整体流程
"""

import asyncio
import contextlib
from uuid import UUID

import logfire

from api.redis.pubsub import subscribe_to_event
from .models import PHASE1_TIMEOUT


async def execute_planning_phase(user_id: UUID, role_name: str) -> bool:
    """
    执行第一阶段：计划更新任务

    通过等待超时机制实现"后来者杀死先来者"的逻辑：
    - 返回 True：超时（没有新任务来抢占），继续执行第二阶段
    - 返回 False：收到新任务的信号，当前任务退出

    参数:
        user_id: 用户 ID
        role_name: 角色名称

    返回:
        bool: True 表示继续执行，False 表示退出任务
    """
    # 订阅 Redis 频道
    channel = f"agent-role-update:planning:{user_id}:{role_name}"
    event = asyncio.Event()

    logfire.info(
        "agent-role-update::phase1_start",
        user_id=str(user_id),
        role_name=role_name,
        timeout=PHASE1_TIMEOUT,
    )

    # 创建订阅任务（在后台运行）
    subscribe_task = asyncio.create_task(subscribe_to_event(channel, event))

    # 等待信号，超时时间为 30 秒
    try:
        await asyncio.wait_for(event.wait(), timeout=PHASE1_TIMEOUT)
        # event.wait() 返回说明收到了信号（有新任务来抢占）
        logfire.info(
            "agent-role-update::phase1_exited_by_newer_task",
            user_id=str(user_id),
            role_name=role_name,
        )
        # 取消订阅任务
        subscribe_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await subscribe_task
        return False

    except TimeoutError:
        # 超时说明没有新任务来抢占，继续执行第二阶段
        logfire.info(
            "agent-role-update::phase1_complete",
            user_id=str(user_id),
            role_name=role_name,
        )
        # 取消订阅任务
        subscribe_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await subscribe_task
        return True
