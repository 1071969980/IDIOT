"""JuiceFS 工作进程池实现

管理工作进程的生命周期，提供任务提交和结果获取接口。
按 meta_url 哈希路由到不同的 worker，避免多个 worker 持有同一个文件系统的连接。
"""

import asyncio
import multiprocessing as mp
from multiprocessing import Queue
from queue import Empty
import time
import threading
import logging
import hashlib
from typing import Any, Dict, Optional, Union, List, Tuple, overload, Literal
import uuid6

import logfire

from api.juiceFS.client_worker.constants import (
    Operation,
    DEFAULT_NUM_WORKERS,
    DEFAULT_MAX_TASKS_PER_WORKER,
    DEFAULT_MAX_CLIENTS_PER_WORKER,
    DEFAULT_TASK_TIMEOUT,
    DEFAULT_QUEUE_PUT_TIMEOUT,
)
from api.juiceFS.client_worker.models import (
    Result,
    OperationOutput,
    OPERATION_REGISTRY,
    get_input_model,
    get_output_model,
    # 导入所有输出类型用于类型重载
    ReadOutput,
    WriteOutput,
    ExistsOutput,
    ListdirOutput,
    MkdirOutput,
    MakedirsOutput,
    RemoveOutput,
    RmdirOutput,
    RmrOutput,
    CloneOutput,
    RenameOutput,
    StatOutput,
    TruncateOutput,
    ChmodOutput,
    GetxattrOutput,
    SetxattrOutput,
    ListxattrOutput,
    RemovexattrOutput,
    BatchOutput,
)
from api.juiceFS.client_worker.worker import create_worker_process
from api.juiceFS.client_worker.exceptions import (
    WorkerPoolError,
    TaskTimeoutError,
    TaskExecutionError,
)

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def hash_meta_url_to_worker(meta_url: str, num_workers: int) -> int:
    """将 meta_url 哈希到 worker ID

    使用 SHA256 哈希确保分布均匀。

    Args:
        meta_url: JuiceFS 元数据地址
        num_workers: worker 数量

    Returns:
        worker ID (0 到 num_workers-1)
    """
    hash_bytes = hashlib.sha256(meta_url.encode()).digest()
    # 取前 8 字节转为整数
    hash_int = int.from_bytes(hash_bytes[:8], byteorder='big')
    return hash_int % num_workers


class JuiceFSWorkerPool:
    """JuiceFS 工作进程池

    管理一组工作进程，提供任务队列模式的 JuiceFS 操作接口。
    按 meta_url 哈希路由到不同的 worker，确保同一文件系统的操作集中在一个 worker。

    使用方法:
        pool = JuiceFSWorkerPool(num_workers=4)
        pool.start()

        # 同步调用
        result = await pool.call(meta_url, Operation.READ, "/path/to/file")

        # 异步调用
        task_id = pool.submit(meta_url, Operation.READ, "/path/to/file")
        result = await pool.get_result(task_id)

        pool.stop()
    """

    def __init__(
        self,
        num_workers: int = DEFAULT_NUM_WORKERS,
        max_tasks_per_worker: int = DEFAULT_MAX_TASKS_PER_WORKER,
        max_clients_per_worker: int = DEFAULT_MAX_CLIENTS_PER_WORKER,
    ):
        """
        初始化工作进程池

        Args:
            num_workers: 工作进程数量
            max_tasks_per_worker: 每个工作进程处理的最大任务数，超过后重启
            max_clients_per_worker: 每个工作进程缓存的最大 Client 数量

        Raises:
            ValueError: 参数验证失败
        """
        # 参数验证
        if num_workers <= 0:
            raise ValueError(f"num_workers must be positive, got {num_workers}")
        if max_tasks_per_worker <= 0:
            raise ValueError(f"max_tasks_per_worker must be positive, got {max_tasks_per_worker}")
        if max_clients_per_worker <= 0:
            raise ValueError(f"max_clients_per_worker must be positive, got {max_clients_per_worker}")

        self.num_workers = num_workers
        self.max_tasks = max_tasks_per_worker
        self.max_clients = max_clients_per_worker

        # 每个 worker 独立的任务队列
        self.task_queues: List[Queue] = []
        # 共享的结果队列
        self.result_queue: Optional[Queue] = None
        self.workers: List[mp.Process] = []
        self._running = False
        # 线程锁保护共享状态
        self._results_lock = threading.Lock()
        # _pending_results 存储 (Result, timestamp) 用于 TTL
        self._pending_results: Dict[str, Tuple[Result, float]] = {}
        # 记录 task_id -> Operation 的映射，用于结果验证
        self._task_operations: Dict[str, Operation] = {}
        # 结果 TTL（秒）
        self._result_ttl = 300

    def start(self):
        """启动工作进程池"""
        if self._running:
            logger.warning("Worker pool already running")
            return

        with logfire.span("juicefs_worker_pool::start"):
            # 为每个 worker 创建独立的任务队列
            self.task_queues = [Queue() for _ in range(self.num_workers)]
            # 共享的结果队列
            self.result_queue = Queue()

            # 初始化所有工作进程
            self._init_workers()

            self._running = True
            logfire.info(
                "Worker pool started",
                num_workers=self.num_workers,
                max_tasks=self.max_tasks,
                max_clients=self.max_clients,
            )

    def _start_worker(self, worker_id: int) -> mp.Process:
        """启动单个工作进程

        Args:
            worker_id: 工作进程 ID

        Returns:
            创建的进程对象
        """
        assert self.result_queue is not None
        task_queue = self.task_queues[worker_id]

        process = create_worker_process(
            worker_id=worker_id,
            task_queue=task_queue,
            result_queue=self.result_queue,
            max_tasks=self.max_tasks,
            max_clients=self.max_clients,
        )
        process.start()
        logger.debug(f"Started worker {worker_id} (pid={process.pid})")
        return process

    def _init_workers(self):
        """初始化所有工作进程"""
        self.workers = []
        for i in range(self.num_workers):
            process = self._start_worker(i)
            self.workers.append(process)

    def _validate_input(self, operation: Operation, args: tuple) -> Dict[str, Any]:
        """验证输入参数

        Args:
            operation: 操作枚举
            args: 位置参数

        Returns:
            验证后的参数字典

        Raises:
            ValueError: 参数验证失败
        """
        input_model_class = get_input_model(operation)
        field_names = list(input_model_class.model_fields.keys())

        if len(args) > len(field_names):
            raise ValueError(
                f"Too many arguments for {operation.value}: "
                f"expected at most {len(field_names)}, got {len(args)}"
            )

        # 转换为字典
        input_dict = {field_names[i]: args[i] for i in range(len(args))}

        # Pydantic 验证
        validated = input_model_class(**input_dict)
        return validated.model_dump()

    def submit(self, meta_url: str, operation: Union[Operation, str], *args) -> str:
        """
        提交任务到工作进程池

        根据 meta_url 哈希到对应的 worker。

        Args:
            meta_url: JuiceFS 元数据地址
            operation: 操作枚举（或字符串，用于兼容）
            *args: 操作参数

        Returns:
            task_id: 任务 ID（UUID v7 字符串），用于获取结果

        Raises:
            WorkerPoolError: 工作进程池未启动
            ValueError: 参数验证失败
        """
        if not self._running:
            raise WorkerPoolError("Worker pool not started")

        # 支持字符串输入，转换为枚举
        if isinstance(operation, str):
            try:
                operation = Operation(operation)
            except ValueError:
                raise ValueError(f"Unknown operation: {operation}")

        # 验证操作名称
        if operation not in OPERATION_REGISTRY:
            raise ValueError(f"Unknown operation: {operation}")

        # 验证输入参数（提前失败，避免无效任务进入队列）
        self._validate_input(operation, args)

        # 检查并重启死亡的 worker（确保任务有 worker 处理）
        self.check_and_restart()

        # 使用 UUID v7 生成唯一 task_id（无需锁保护）
        task_id = str(uuid6.uuid7())

        # 记录操作类型，用于结果验证
        with self._results_lock:
            self._task_operations[task_id] = operation

        # 按 meta_url 哈希到 worker
        worker_id = hash_meta_url_to_worker(meta_url, self.num_workers)
        task_queue = self.task_queues[worker_id]

        # 序列化：将枚举值作为字符串传递
        # 使用带超时的 put，避免高负载下永久阻塞
        try:
            task_queue.put(
                (task_id, meta_url, operation.value, args),
                timeout=DEFAULT_QUEUE_PUT_TIMEOUT,
            )
        except Exception as e:
            # put 超时，清理已记录的操作并抛出异常
            with self._results_lock:
                self._task_operations.pop(task_id, None)
            raise WorkerPoolError(
                f"Task queue full, failed to submit task after {DEFAULT_QUEUE_PUT_TIMEOUT}s: {e}"
            )

        logfire.debug(
            "Task submitted",
            task_id=task_id,
            operation=operation.value,
            meta_url=meta_url,
            worker_id=worker_id,
        )

        return task_id

    def get_result(self, task_id: str, timeout: float = DEFAULT_TASK_TIMEOUT) -> OperationOutput:
        """
        获取任务结果

        Args:
            task_id: 任务 ID
            timeout: 超时时间（秒）

        Returns:
            验证后的输出模型实例

        Raises:
            WorkerPoolError: 工作进程池未启动
            TaskTimeoutError: 任务超时
            TaskExecutionError: 任务执行错误
        """
        if not self._running:
            raise WorkerPoolError("Worker pool not started")

        assert self.result_queue is not None  # 类型守卫

        deadline = time.time() + timeout

        while time.time() < deadline:
            # 清理过期结果
            self._cleanup_expired_results()

            # 先检查缓存的结果（使用锁保护）
            with self._results_lock:
                if task_id in self._pending_results:
                    result, _ = self._pending_results.pop(task_id)
                    return self._process_result(result, task_id)

            # 从共享队列获取新结果
            try:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                result_data = self.result_queue.get(timeout=remaining)

                # 处理可能是 tuple 或 Result 对象的情况
                if isinstance(result_data, tuple):
                    result = Result(*result_data)
                else:
                    result = result_data

                if result.task_id == task_id:
                    return self._process_result(result, task_id)
                else:
                    # 缓存其他任务的结果（带时间戳）
                    with self._results_lock:
                        self._pending_results[result.task_id] = (result, time.time())
            except Empty:
                continue

        # 清理 task_operations（使用锁保护）
        with self._results_lock:
            self._task_operations.pop(task_id, None)
        raise TaskTimeoutError(f"Task {task_id} timed out after {timeout}s")

    def _cleanup_expired_results(self):
        """清理过期的缓存结果

        移除超过 TTL 时间的结果，防止内存泄漏。
        """
        now = time.time()
        with self._results_lock:
            expired_keys = [
                task_id for task_id, (_, timestamp) in self._pending_results.items()
                if now - timestamp > self._result_ttl
            ]
            for key in expired_keys:
                del self._pending_results[key]
                # 同时清理对应的 task_operations
                self._task_operations.pop(key, None)

    def _process_result(self, result: Result, task_id: str) -> OperationOutput:
        """处理并验证结果

        Args:
            result: 结果对象
            task_id: 任务 ID（UUID v7 字符串）

        Returns:
            验证后的输出模型实例

        Raises:
            TaskExecutionError: 任务执行错误或结果验证失败
        """
        try:
            if result.status == "error":
                raise TaskExecutionError(
                    message=result.error_msg or "Unknown error",
                    task_id=result.task_id,
                )

            # 获取对应的输出模型（使用锁保护）
            with self._results_lock:
                operation = self._task_operations.pop(task_id, None)
            if operation is None:
                # 无法验证，返回原始数据并警告
                logger.warning(f"No operation found for task {task_id}, skipping validation")
                # 返回一个通用的输出包装
                return OperationOutput()

            output_model_class = get_output_model(operation)

            # 验证输出数据
            if isinstance(result.data, dict):
                validated_output = output_model_class(**result.data)
            else:
                # 如果返回的不是字典，尝试直接构造
                # 这种情况可能是 Worker 返回了非预期格式
                raise TaskExecutionError(
                    message=f"Invalid result format: expected dict, got {type(result.data)}",
                    task_id=result.task_id,
                )

            return validated_output

        except TaskExecutionError:
            raise
        except Exception as e:
            raise TaskExecutionError(
                message=f"Result validation failed: {e}",
                task_id=result.task_id,
            )

    # ============================================================
    # 类型重载定义
    #
    # 使用 Literal 类型区分不同操作，让 IDE 能够推断正确的返回类型。
    # 注意：这些重载仅用于类型提示，运行时仍使用实际实现。
    # ============================================================

    @overload
    async def call(
        self,
        meta_url: str,
        operation: Literal[Operation.READ],
        *args: Any,
        timeout: float = DEFAULT_TASK_TIMEOUT,
    ) -> ReadOutput: ...

    @overload
    async def call(
        self,
        meta_url: str,
        operation: Literal[Operation.WRITE],
        *args: Any,
        timeout: float = DEFAULT_TASK_TIMEOUT,
    ) -> WriteOutput: ...

    @overload
    async def call(
        self,
        meta_url: str,
        operation: Literal[Operation.EXISTS],
        *args: Any,
        timeout: float = DEFAULT_TASK_TIMEOUT,
    ) -> ExistsOutput: ...

    @overload
    async def call(
        self,
        meta_url: str,
        operation: Literal[Operation.LISTDIR],
        *args: Any,
        timeout: float = DEFAULT_TASK_TIMEOUT,
    ) -> ListdirOutput: ...

    @overload
    async def call(
        self,
        meta_url: str,
        operation: Literal[Operation.MKDIR],
        *args: Any,
        timeout: float = DEFAULT_TASK_TIMEOUT,
    ) -> MkdirOutput: ...

    @overload
    async def call(
        self,
        meta_url: str,
        operation: Literal[Operation.MKDIRS],
        *args: Any,
        timeout: float = DEFAULT_TASK_TIMEOUT,
    ) -> MakedirsOutput: ...

    @overload
    async def call(
        self,
        meta_url: str,
        operation: Literal[Operation.REMOVE],
        *args: Any,
        timeout: float = DEFAULT_TASK_TIMEOUT,
    ) -> RemoveOutput: ...

    @overload
    async def call(
        self,
        meta_url: str,
        operation: Literal[Operation.RMDIR],
        *args: Any,
        timeout: float = DEFAULT_TASK_TIMEOUT,
    ) -> RmdirOutput: ...

    @overload
    async def call(
        self,
        meta_url: str,
        operation: Literal[Operation.RMR],
        *args: Any,
        timeout: float = DEFAULT_TASK_TIMEOUT,
    ) -> RmrOutput: ...

    @overload
    async def call(
        self,
        meta_url: str,
        operation: Literal[Operation.CLONE],
        *args: Any,
        timeout: float = DEFAULT_TASK_TIMEOUT,
    ) -> CloneOutput: ...

    @overload
    async def call(
        self,
        meta_url: str,
        operation: Literal[Operation.RENAME],
        *args: Any,
        timeout: float = DEFAULT_TASK_TIMEOUT,
    ) -> RenameOutput: ...

    @overload
    async def call(
        self,
        meta_url: str,
        operation: Literal[Operation.STAT],
        *args: Any,
        timeout: float = DEFAULT_TASK_TIMEOUT,
    ) -> StatOutput: ...

    @overload
    async def call(
        self,
        meta_url: str,
        operation: Literal[Operation.TRUNCATE],
        *args: Any,
        timeout: float = DEFAULT_TASK_TIMEOUT,
    ) -> TruncateOutput: ...

    @overload
    async def call(
        self,
        meta_url: str,
        operation: Literal[Operation.CHMOD],
        *args: Any,
        timeout: float = DEFAULT_TASK_TIMEOUT,
    ) -> ChmodOutput: ...

    @overload
    async def call(
        self,
        meta_url: str,
        operation: Literal[Operation.GETXATTR],
        *args: Any,
        timeout: float = DEFAULT_TASK_TIMEOUT,
    ) -> GetxattrOutput: ...

    @overload
    async def call(
        self,
        meta_url: str,
        operation: Literal[Operation.SETXATTR],
        *args: Any,
        timeout: float = DEFAULT_TASK_TIMEOUT,
    ) -> SetxattrOutput: ...

    @overload
    async def call(
        self,
        meta_url: str,
        operation: Literal[Operation.LISTXATTR],
        *args: Any,
        timeout: float = DEFAULT_TASK_TIMEOUT,
    ) -> ListxattrOutput: ...

    @overload
    async def call(
        self,
        meta_url: str,
        operation: Literal[Operation.REMOVEXATTR],
        *args: Any,
        timeout: float = DEFAULT_TASK_TIMEOUT,
    ) -> RemovexattrOutput: ...

    @overload
    async def call(
        self,
        meta_url: str,
        operation: Literal[Operation.BATCH],
        *args: Any,
        timeout: float = DEFAULT_TASK_TIMEOUT,
    ) -> BatchOutput: ...

    @overload
    async def call(
        self,
        meta_url: str,
        operation: str,
        *args: Any,
        timeout: float = DEFAULT_TASK_TIMEOUT,
    ) -> OperationOutput: ...

    async def call(
        self,
        meta_url: str,
        operation: Union[Operation, str],
        *args: Any,
        timeout: float = DEFAULT_TASK_TIMEOUT,
    ) -> OperationOutput:
        """
        异步调用（提交并等待结果）

        将阻塞的 get_result 调用放到线程池中执行，避免阻塞事件循环。

        Args:
            meta_url: JuiceFS 元数据地址
            operation: 操作枚举
            *args: 操作参数
            timeout: 超时时间

        Returns:
            验证后的输出模型实例
        """
        with logfire.span(
            "juicefs_worker_pool::call",
            operation=operation.value if isinstance(operation, Operation) else operation,
            meta_url=meta_url,
        ):
            task_id = self.submit(meta_url, operation, *args)
            # 将阻塞调用放到线程池中，避免阻塞事件循环
            result = await asyncio.to_thread(self.get_result, task_id, timeout)

            logfire.info(
                "Task completed",
                task_id=task_id,
                operation=operation.value if isinstance(operation, Operation) else operation,
            )

            return result

    def call_sync(
        self,
        meta_url: str,
        operation: Union[Operation, str],
        *args: Any,
        timeout: float = DEFAULT_TASK_TIMEOUT,
    ) -> OperationOutput:
        """
        同步调用版本（阻塞当前线程）

        用于不支持异步的场景。

        Args:
            meta_url: JuiceFS 元数据地址
            operation: 操作枚举
            *args: 操作参数
            timeout: 超时时间

        Returns:
            验证后的输出模型实例
        """
        task_id = self.submit(meta_url, operation, *args)
        return self.get_result(task_id, timeout)

    async def batch_call(
        self,
        meta_url: str,
        operations: list[tuple[Union[Operation, str], ...]],
        stop_on_error: bool = False,
        timeout: float = DEFAULT_TASK_TIMEOUT,
    ):
        """
        批量执行多个操作

        Args:
            meta_url: JuiceFS 元数据地址
            operations: 操作列表，每个元素是 (operation, *args) 元组
            stop_on_error: 遇到错误时是否停止
            timeout: 超时时间

        Returns:
            BatchOutput 包含每个操作的结果

        Example:
            result = await pool.batch_call(
                meta_url,
                [
                    (Operation.MKDIRS, "/data/dir1"),
                    (Operation.WRITE, "/data/dir1/file.txt", b"hello"),
                    (Operation.READ, "/data/dir1/file.txt"),
                ]
            )
        """
        from api.juiceFS.client_worker.models import (
            BatchInput,
            BatchOutput,
            BatchOperationItem,
        )

        # 构建批量操作输入
        batch_ops = [
            BatchOperationItem(
                operation=op.value if isinstance(op, Operation) else op,
                args=list(args),
            )
            for op, *args in operations
        ]

        batch_input = BatchInput(
            operations=batch_ops,
            stop_on_error=stop_on_error,
        )

        with logfire.span(
            "juicefs_worker_pool::batch_call",
            meta_url=meta_url,
            num_operations=len(operations),
        ):
            result = await self.call(
                meta_url,
                Operation.BATCH,
                batch_input.operations,
                batch_input.stop_on_error,
                timeout=timeout,
            )

            return BatchOutput.model_validate(result.model_dump())

    def restart_workers(self):
        """重启所有工作进程

        用于定期释放资源，控制内存使用。

        注意：这会丢弃所有队列中未处理的任务，等待中的请求会超时。
        """
        with logfire.span("juicefs_worker_pool::restart_workers"):
            logger.info("Restarting all workers...")

            # 发送停止信号到所有 worker 的队列
            for task_queue in self.task_queues:
                try:
                    task_queue.put(None, timeout=1)
                except Exception:
                    pass

            # 等待进程结束
            for p in self.workers:
                p.join(timeout=5)
                if p.is_alive():
                    p.terminate()

            # 清理
            self.workers.clear()
            with self._results_lock:
                self._pending_results.clear()
                self._task_operations.clear()

            # 重新创建队列和启动进程
            # 注意：旧队列中未处理的任务会被丢弃
            self.task_queues = [Queue() for _ in range(self.num_workers)]
            self.result_queue = Queue()

            # 初始化所有工作进程
            self._init_workers()

            logfire.info("Workers restarted", num_workers=self.num_workers)

    def check_and_restart(self):
        """检查工作进程状态，必要时重启已退出的进程

        重启死亡进程时，保持队列不变（队列中可能有未处理的任务）。
        """
        dead_workers = [
            i for i, p in enumerate(self.workers) if not p.is_alive()
        ]

        if dead_workers:
            logfire.warning(
                "Found dead workers, restarting",
                dead_worker_ids=dead_workers,
            )
            for worker_id in dead_workers:
                # 等待死亡进程完全退出
                self.workers[worker_id].join()
                # 替换死亡的进程（而不是 append）
                new_process = self._start_worker(worker_id)
                self.workers[worker_id] = new_process

    def stop(self):
        """停止工作进程池"""
        if not self._running:
            return

        with logfire.span("juicefs_worker_pool::stop"):
            logger.info("Stopping worker pool...")

            # 发送停止信号到所有 worker 的队列
            for task_queue in self.task_queues:
                try:
                    task_queue.put(None, timeout=1)
                except Exception:
                    pass

            # 等待进程结束
            for p in self.workers:
                p.join(timeout=5)
                if p.is_alive():
                    p.terminate()

            self.workers.clear()
            self.task_queues.clear()
            self._running = False
            with self._results_lock:
                self._task_operations.clear()

            logfire.info("Worker pool stopped")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb):
        self.stop()
        return False

    @property
    def is_running(self) -> bool:
        """工作进程池是否正在运行"""
        return self._running

    @property
    def active_workers(self) -> int:
        """活跃的工作进程数量"""
        return sum(1 for p in self.workers if p.is_alive())