"""JuiceFS 多租户客户端工作进程池

解决 JuiceFS Python SDK 在多租户场景下的资源泄漏问题。
使用任务队列模式，通过进程隔离和定期重启来控制资源使用。

架构特点:
- 按 meta_url 哈希路由到不同的 worker
- 每个 worker 有独立的任务队列
- 同一文件系统的操作集中在一个 worker，LRU 缓存更有效

使用方法:
    # 在 FastAPI lifespan 中初始化
    from api.juiceFS.client_worker import init_worker_pool, close_worker_pool

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_worker_pool()
        yield
        close_worker_pool()

    # 业务代码中使用
    from api.juiceFS.client_worker import get_worker_pool, Operation

    pool = get_worker_pool()
    result = await pool.call(meta_url, Operation.READ, "/path/to/file")
    content = result.content  # 类型安全的属性访问
"""

from api.juiceFS.client_worker.constants import Operation
from api.juiceFS.client_worker.pool import JuiceFSWorkerPool, hash_meta_url_to_worker
from api.juiceFS.client_worker.lifespan import (
    init_worker_pool,
    close_worker_pool,
    get_worker_pool,
)

__all__ = [
    # 枚举
    "Operation",
    # 进程池
    "JuiceFSWorkerPool",
    # 路由函数
    "hash_meta_url_to_worker",
    # 生命周期管理
    "init_worker_pool",
    "close_worker_pool",
    "get_worker_pool",
]