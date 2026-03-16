"""FastAPI lifespan 集成

提供应用级别的单例工作进程池管理。
"""

from typing import Optional

import logfire

from api.juiceFS.client_worker.pool import JuiceFSWorkerPool
from api.juiceFS.client_worker.exceptions import WorkerPoolNotInitializedError

# 全局单例
_worker_pool: Optional[JuiceFSWorkerPool] = None


def init_worker_pool(
    num_workers: int = 4,
    max_tasks_per_worker: int = 500,
    max_clients_per_worker: int = 20,
) -> JuiceFSWorkerPool:
    """
    初始化全局工作进程池

    应在 FastAPI lifespan 中调用。

    Args:
        num_workers: 工作进程数量
        max_tasks_per_worker: 每个工作进程处理的最大任务数
        max_clients_per_worker: 每个工作进程缓存的最大 Client 数量

    Returns:
        工作进程池实例
    """
    global _worker_pool

    if _worker_pool is not None and _worker_pool.is_running:
        logfire.warning("Worker pool already initialized and running")
        return _worker_pool

    _worker_pool = JuiceFSWorkerPool(
        num_workers=num_workers,
        max_tasks_per_worker=max_tasks_per_worker,
        max_clients_per_worker=max_clients_per_worker,
    )
    _worker_pool.start()

    logfire.info(
        "JuiceFS worker pool initialized",
        num_workers=num_workers,
        max_tasks_per_worker=max_tasks_per_worker,
        max_clients_per_worker=max_clients_per_worker,
    )

    return _worker_pool


def close_worker_pool():
    """
    关闭全局工作进程池

    应在 FastAPI lifespan 中调用。
    """
    global _worker_pool

    if _worker_pool is not None:
        _worker_pool.stop()
        _worker_pool = None
        logfire.info("JuiceFS worker pool closed")


def get_worker_pool() -> JuiceFSWorkerPool:
    """
    获取全局工作进程池

    Returns:
        工作进程池实例

    Raises:
        WorkerPoolNotInitializedError: 工作进程池未初始化
    """
    if _worker_pool is None:
        raise WorkerPoolNotInitializedError(
            "Worker pool not initialized. Call init_worker_pool() first."
        )
    return _worker_pool


def is_worker_pool_initialized() -> bool:
    """
    检查工作进程池是否已初始化

    Returns:
        是否已初始化
    """
    return _worker_pool is not None and _worker_pool.is_running