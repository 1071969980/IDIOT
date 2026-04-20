import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Union
from uuid import UUID

import logfire

from api.app.chat.process_pending_messages import _process_pending_messages
from api.chat.sql_stat.u2a_session_branch.utils import (
    get_branch_by_session_and_name,
)
from api.chat.sql_stat.u2a_session_task.utils import (
    get_ancestors_by_leaf_task_and_statuses,
    get_task,
)
from api.redis.distributed_lock import RedisDistributedLock
from api.redis.event_names import EventNames
from api.redis.lock_names import LockNames
from api.redis.redis_event import RedisEvent

logger = logging.getLogger(__name__)


async def schedule_pending_task(
    user_id: UUID,
    session_id: UUID,
    branch_name: str,
    llm_service_name: str,
    before_process: Callable[..., Union[None, Awaitable[None]]] | None = None,
) -> None:
    """在当前 processing task 完成后，尝试运行分支上的 pending task。

    执行流程：
    0. 检查是否已有等待/处理中的任务（通过锁的 is_locked），有则返回
    1. 获取分布式锁包裹主要逻辑
    2. 找到 pending task 及其父节点 processing task
    3. 同时等待自身取消事件和父节点 task 完成事件（超时 10 min）
    4. 状态校验后，在锁外启动 _process_pending_messages 处理 pending task
    """
    lock_key = LockNames.schedule_pending_task(session_id, branch_name)
    lock = RedisDistributedLock(key=lock_key)

    # 0. 如果锁已被持有，说明已有等待/处理中的任务
    if await lock.is_locked():
        return

    # 1. 获取分布式锁
    async with lock:
        should_process = await _schedule_pending_task_inner(
            user_id=user_id,
            session_id=session_id,
            branch_name=branch_name,
        )

    # 在锁外启动 _process_pending_messages，避免 MultiLockError
    if should_process:
        if before_process is not None:
            result = before_process(user_id, session_id, branch_name, llm_service_name)
            if isinstance(result, Awaitable):
                await result

        asyncio.create_task(_process_pending_messages(  # noqa: RUF006
            user_id=user_id,
            session_id=session_id,
            branch_name=branch_name,
            llm_service_name=llm_service_name,
        ))


async def _schedule_pending_task_inner(
    user_id: UUID,
    session_id: UUID,
    branch_name: str,
) -> bool:
    """返回 True 表示应启动 _process_pending_messages，False 表示放弃。"""
    with logfire.span(
        "api/chat/schedule_pending_task.py::schedule_pending_task",
        user_id=str(user_id),
        session_id=str(session_id),
        branch_name=branch_name,
    ):
        # 2.1 查找分支
        branch = await get_branch_by_session_and_name(session_id, branch_name)
        if branch is None:
            logfire.info("schedule_pending_task: 分支不存在", branch_name=branch_name)
            return False

        # 2.2 获取 leaf task 并验证是否为 pending
        leaf_task = await get_task(branch.leaf_task_id)
        if leaf_task is None:
            logfire.info("schedule_pending_task: leaf task 不存在", leaf_task_id=str(branch.leaf_task_id))
            return False
        if leaf_task.status != "pending":
            logfire.info("schedule_pending_task: leaf task 非 pending 状态", leaf_task_id=str(leaf_task.id), status=leaf_task.status)
            return False

        # 记录状态快照，用于后续一致性校验
        snapshot_leaf_task_id = leaf_task.id
        snapshot_branch_id = branch.id

        # 2.3 查找该分支路径上的 processing 祖先任务
        processing_ancestors = await get_ancestors_by_leaf_task_and_statuses(
            leaf_task.id, ["processing"]
        )

        if not processing_ancestors:
            logfire.info("schedule_pending_task: 无 processing 祖先任务", leaf_task_id=str(leaf_task.id))
            return False

        parent_task_id = processing_ancestors[-1].id

        # 3. 同时等待 schedule 取消事件和父节点 task 完成事件
        cancel_event = RedisEvent(EventNames.schedule_pending_task_canceled(session_id, branch_name))
        completed_event = RedisEvent(EventNames.session_task_completed(parent_task_id))

        try:
            await asyncio.wait(
                [
                    asyncio.create_task(cancel_event.wait()),
                    asyncio.create_task(completed_event.wait(timeout=600)),
                ],
                timeout=600,  # 10 min
                return_when=asyncio.FIRST_COMPLETED,
            )
        except asyncio.TimeoutError:
            logfire.info("schedule_pending_task: 等待事件超时", parent_task_id=str(parent_task_id))
            return False

        # 3.1 取消或超时则返回
        if cancel_event.is_set():
            logfire.info("schedule_pending_task: 收到取消事件")
            return False

        if not completed_event.is_set():
            logfire.info("schedule_pending_task: 父节点任务未完成", parent_task_id=str(parent_task_id))
            return False

        # 4. 状态一致性校验
        # 4.1 通过 session_id + branch_name 重新获取 branch，确认 leaf_task_id 未变
        branch_now = await get_branch_by_session_and_name(session_id, branch_name)
        if branch_now is None:
            logfire.info("schedule_pending_task: 校验时分支已不存在", branch_name=branch_name)
            return False
        if branch_now.leaf_task_id != snapshot_leaf_task_id:
            logfire.info("schedule_pending_task: branch leaf_task_id 已变更", expected=str(snapshot_leaf_task_id), actual=str(branch_now.leaf_task_id))
            return False

        # 4.2 确认 leaf task 仍被相同 branch 引用
        leaf_task_now = await get_task(snapshot_leaf_task_id)
        if leaf_task_now is None:
            logfire.info("schedule_pending_task: 校验时 leaf task 已不存在", leaf_task_id=str(snapshot_leaf_task_id))
            return False
        if leaf_task_now.branch_id != snapshot_branch_id:
            logfire.info("schedule_pending_task: leaf task branch_id 已变更", expected=str(snapshot_branch_id), actual=str(leaf_task_now.branch_id))
            return False
        
        return True
