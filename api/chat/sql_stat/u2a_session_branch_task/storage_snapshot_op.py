from typing import Any, Callable
from uuid import UUID

from api.chat.sql_stat.u2a_session_task.utils import (
    get_task,
    update_task_storage_snapshot,
)
from api.chat.sql_stat.u2a_session_branch_task.operations import (
    get_or_create_pending_task,
)
from api.redis.distributed_lock import RedisDistributedLock
from api.redis.lock_names import LockNames


async def get_branch_storage_snapshot(
    session_id: UUID,
    user_id: UUID,
    branch_name: str,
) -> tuple[UUID, dict[str, Any]]:
    """获取指定分支 pending task 的 storage_snapshot

    Args:
        session_id: 会话ID
        user_id: 用户ID
        branch_name: 分支名称

    Returns:
        (task_id, storage_snapshot)
    """
    task_id, _ = await get_or_create_pending_task(
        session_id=session_id,
        user_id=user_id,
        branch_name=branch_name,
    )
    task = await get_task(task_id)
    if task is None or task.storage_snapshot is None:
        raise ValueError(f"Task {task_id} or its storage_snapshot not found")
    return task_id, dict(task.storage_snapshot)


async def update_branch_storage_snapshot(
    session_id: UUID,
    user_id: UUID,
    branch_name: str,
    update_fn: Callable[[dict[str, Any]], bool],
) -> tuple[UUID, dict[str, Any]]:
    """在分布式锁保护下读取、就地修改、写回分支的 storage_snapshot

    update_fn 接收 snapshot dict，就地修改后返回 True 以触发持久化；
    返回 False 可跳过写入（用于无变更场景）。

    Args:
        session_id: 会话ID
        user_id: 用户ID
        branch_name: 分支名称
        update_fn: 就地修改 snapshot 的回调函数，返回 True 持久化，False 跳过

    Returns:
        (task_id, modified_snapshot)
    """
    task_id, _ = await get_or_create_pending_task(
        session_id=session_id,
        user_id=user_id,
        branch_name=branch_name,
    )
    lock_key = LockNames.task_storage_snapshot(task_id)
    async with RedisDistributedLock(lock_key, allow_multi_lock=True):
        task = await get_task(task_id)
        if task is None or task.storage_snapshot is None:
            raise ValueError(f"Task {task_id} or its storage_snapshot not found")
        snapshot = dict(task.storage_snapshot)
        should_save = update_fn(snapshot)
        if should_save:
            await update_task_storage_snapshot(task_id, snapshot)
    return task_id, snapshot
