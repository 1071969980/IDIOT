"""JuiceFS 工作进程实现

工作进程运行在独立进程中，负责执行 JuiceFS 操作。
通过 LRU 缓存管理 Client 实例，达到任务上限后自动退出。
"""

import multiprocessing as mp
from multiprocessing import Queue
from pathlib import PurePosixPath
from queue import Empty
import os
import traceback
import logging
from typing import Any, Optional, Callable

from api.juiceFS.client_worker.constants import (
    Operation,
    WORKER_IDLE_TIMEOUT,
)
from api.juiceFS.client_worker.models import (
    Task,
    Result,
    OperationInput,
    OPERATION_REGISTRY,
    ENTRY_TYPE_MAP,
    # 输入模型（用于类型断言）
    ReadInput,
    WriteInput,
    ExistsInput,
    ListdirInput,
    MkdirInput,
    MakedirsInput,
    RemoveInput,
    RmdirInput,
    RmrInput,
    CloneInput,
    RenameInput,
    StatInput,
    TruncateInput,
    ChmodInput,
    GetxattrInput,
    SetxattrInput,
    ListxattrInput,
    RemovexattrInput,
    ListtreeInput,
    # 批量操作
    BatchInput,
)
from api.juiceFS.client_worker.lru_cache import LRUCache

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class JuiceFSWorker:
    """JuiceFS 工作进程

    在独立进程中运行，通过任务队列接收任务，执行 JuiceFS 操作。
    使用 LRU 缓存管理 Client 实例，避免资源过度使用。
    """

    def __init__(
        self,
        task_queue: Queue,
        result_queue: Queue,
        worker_id: int,
        max_tasks: int = 500,
        max_clients: int = 20,
        client_factory: Optional[Callable] = None,
    ):
        """
        初始化工作进程

        Args:
            task_queue: 任务队列
            result_queue: 结果队列
            worker_id: 工作进程 ID
            max_tasks: 最大处理任务数，超过后自动退出
            max_clients: 最大缓存的 Client 数量
            client_factory: Client 工厂函数，用于测试
        """
        self.task_queue = task_queue
        self.result_queue = result_queue
        self.worker_id = worker_id
        self.max_tasks = max_tasks
        self.max_clients = max_clients
        self.client_factory = client_factory

    def run(self):
        """工作进程主循环

        持续从任务队列获取任务并执行，直到：
        1. 收到 None 信号（关闭）
        2. 空闲超时
        3. 达到最大任务数
        """
        # 延迟导入，避免 fork 问题
        from juicefs import Client

        # 使用工厂函数或默认 Client 类
        ClientClass = self.client_factory or Client

        # Client 缓存
        clients = LRUCache(max_size=self.max_clients)
        task_count = 0

        logger.info(f"Worker {self.worker_id} started, max_tasks={self.max_tasks}")

        while True:
            try:
                # 带超时的获取，允许空闲退出
                task_data = self.task_queue.get(timeout=WORKER_IDLE_TIMEOUT)
            except Empty:
                logger.info(f"Worker {self.worker_id} idle timeout, exiting")
                break

            if task_data is None:
                logger.info(f"Worker {self.worker_id} received shutdown signal")
                break

            task = Task(*task_data)
            result = self._handle_task(task, clients, ClientClass)
            self.result_queue.put(result)

            task_count += 1

            # 达到任务上限，退出让主进程重启
            if task_count >= self.max_tasks:
                logger.info(
                    f"Worker {self.worker_id} reached max_tasks ({self.max_tasks}), restarting"
                )
                break

        # 清理资源
        clients.clear()
        logger.info(f"Worker {self.worker_id} stopped")

    def _handle_task(
        self, task: Task, clients: LRUCache, ClientClass
    ) -> Result:
        """处理单个任务

        Args:
            task: 任务定义
            clients: Client 缓存
            ClientClass: Client 类

        Returns:
            任务执行结果
        """
        try:
            # 将字符串操作转换为枚举
            try:
                operation = Operation(task.operation)
            except ValueError:
                return Result(
                    task_id=task.task_id,
                    status="error",
                    data=None,
                    error_msg=f"Unsupported operation: {task.operation}",
                )

            # 解析输入参数
            input_model_class, _ = OPERATION_REGISTRY[operation]
            try:
                # 将 args 转换为字典
                input_dict = self._args_to_dict(operation, task.args)
                input_model = input_model_class(**input_dict)
            except Exception as e:
                return Result(
                    task_id=task.task_id,
                    status="error",
                    data=None,
                    error_msg=f"Invalid input arguments: {e}",
                )

            # 获取或创建 Client
            client = clients.get(task.meta_url)
            if client is None:
                client = ClientClass("volume", meta=task.meta_url)
                evicted = clients.put(task.meta_url, client)
                if evicted:
                    logger.debug(
                        f"Worker {self.worker_id} evicted client for {evicted}"
                    )

            # 执行操作
            raw_result = self._execute_operation(client, operation, input_model)

            return Result(
                task_id=task.task_id,
                status="ok",
                data=raw_result,
            )

        except Exception as e:
            logger.error(
                f"Worker {self.worker_id} error: {e}\n{traceback.format_exc()}"
            )
            return Result(
                task_id=task.task_id,
                status="error",
                data=None,
                error_msg=str(e),
            )

    def _args_to_dict(self, operation: Operation, args: tuple) -> dict:
        """将位置参数转换为字典

        根据操作的输入模型字段顺序，将 tuple 转换为 dict。
        """
        input_model_class, _ = OPERATION_REGISTRY[operation]
        field_names = list(input_model_class.model_fields.keys())

        if len(args) > len(field_names):
            raise ValueError(
                f"Too many arguments for {operation.value}: "
                f"expected at most {len(field_names)}, got {len(args)}"
            )

        return {field_names[i]: args[i] for i in range(len(args))}

    def _execute_operation(
        self, client, operation: Operation, input_model: OperationInput
    ) -> Any:
        """执行文件系统操作

        Args:
            client: JuiceFS Client 实例
            operation: 操作枚举
            input_model: 验证后的输入参数模型

        Returns:
            操作结果（原始数据字典，由 pool 进行验证）

        Raises:
            ValueError: 不支持的操作
        """
        # 已验证: 基于 juicefs Python SDK 实际 API 实现
        # 验证来源: .venv/lib/python3.13/site-packages/juicefs/juicefs.py

        from juicefs import Client
        assert isinstance(client, Client)

        if operation == Operation.READ:
            assert isinstance(input_model, ReadInput)
            with client.open(input_model.path, "rb") as f:
                return {"content": f.read()}

        elif operation == Operation.WRITE:
            assert isinstance(input_model, WriteInput)
            with client.open(input_model.path, "wb") as f:
                written = f.write(input_model.data)
            return {"bytes_written": written}

        elif operation == Operation.EXISTS:
            assert isinstance(input_model, ExistsInput)
            return {"exists": client.exists(input_model.path)}

        elif operation == Operation.LISTDIR:
            assert isinstance(input_model, ListdirInput)
            entries = client.listdir(
                input_model.path,
                detail=input_model.detail
            )
            # 如果 detail=True，entries 是 list[tuple[str, os.stat_result]]
            # 需要将 os.stat_result 转换为字典
            if input_model.detail:
                converted_entries = []
                for name, stat_result in entries:
                    converted_entries.append({
                        "name": name,
                        "st_mode": stat_result.st_mode,
                        "st_ino": stat_result.st_ino,
                        "st_dev": stat_result.st_dev,
                        "st_nlink": stat_result.st_nlink,
                        "st_uid": stat_result.st_uid,
                        "st_gid": stat_result.st_gid,
                        "st_size": stat_result.st_size,
                        "st_atime": stat_result.st_atime,
                        "st_mtime": stat_result.st_mtime,
                        "st_ctime": stat_result.st_ctime,
                    })
                return {"entries": converted_entries}
            return {"entries": entries}

        elif operation == Operation.MKDIR:
            assert isinstance(input_model, MkdirInput)
            client.mkdir(input_model.path, input_model.mode)
            return {"success": True}

        elif operation == Operation.MKDIRS:
            assert isinstance(input_model, MakedirsInput)
            client.makedirs(
                input_model.path,
                input_model.mode,
                input_model.exist_ok
            )
            return {"success": True}

        elif operation == Operation.REMOVE:
            assert isinstance(input_model, RemoveInput)
            client.remove(input_model.path)
            return {"success": True}

        elif operation == Operation.RMDIR:
            assert isinstance(input_model, RmdirInput)
            client.rmdir(input_model.path)
            return {"success": True}

        elif operation == Operation.RMR:
            assert isinstance(input_model, RmrInput)
            client.rmr(input_model.path)
            return {"success": True}

        elif operation == Operation.CLONE:
            assert isinstance(input_model, CloneInput)
            client.clone(input_model.src, input_model.dst, input_model.preserve)
            return {"success": True}

        elif operation == Operation.RENAME:
            assert isinstance(input_model, RenameInput)
            client.rename(input_model.old, input_model.new)
            return {"success": True}

        elif operation == Operation.STAT:
            assert isinstance(input_model, StatInput)
            # stat() 返回 os.stat_result，需要转换为字典
            stat_result = client.stat(input_model.path)
            return {
                "stat_info": {
                    "name": os.path.basename(input_model.path),
                    "st_mode": stat_result.st_mode,
                    "st_ino": stat_result.st_ino,
                    "st_dev": stat_result.st_dev,
                    "st_nlink": stat_result.st_nlink,
                    "st_uid": stat_result.st_uid,
                    "st_gid": stat_result.st_gid,
                    "st_size": stat_result.st_size,
                    "st_atime": stat_result.st_atime,
                    "st_mtime": stat_result.st_mtime,
                    "st_ctime": stat_result.st_ctime,
                }
            }

        elif operation == Operation.TRUNCATE:
            assert isinstance(input_model, TruncateInput)
            client.truncate(input_model.path, input_model.size)
            return {"success": True}

        elif operation == Operation.CHMOD:
            assert isinstance(input_model, ChmodInput)
            client.chmod(input_model.path, input_model.mode)
            return {"success": True}

        elif operation == Operation.GETXATTR:
            assert isinstance(input_model, GetxattrInput)
            value = client.getxattr(input_model.path, input_model.name)
            return {"value": value}

        elif operation == Operation.SETXATTR:
            assert isinstance(input_model, SetxattrInput)
            client.setxattr(
                input_model.path,
                input_model.name,
                input_model.value,
                input_model.flags
            )
            return {"success": True}

        elif operation == Operation.LISTXATTR:
            assert isinstance(input_model, ListxattrInput)
            names = client.listxattr(input_model.path)
            return {"names": names}

        elif operation == Operation.REMOVEXATTR:
            assert isinstance(input_model, RemovexattrInput)
            client.removexattr(input_model.path, input_model.name)
            return {"success": True}

        elif operation == Operation.LISTTREE:
            assert isinstance(input_model, ListtreeInput)
            path_str = str(input_model.path)
            result = client.summary(path_str, input_model.depth, input_model.entries)
            self._convert_summary_type(result)
            self._normalize_summary_paths(result, PurePosixPath(path_str).name)
            return {"summary": result}

        elif operation == Operation.BATCH:
            assert isinstance(input_model, BatchInput)
            return self._execute_batch(client, input_model)

        else:
            raise ValueError(f"Unknown operation: {operation}")

    @staticmethod
    def _convert_summary_type(entry: dict):
        """将 summary 返回中的 Type 从 int 转换为字符串字面量（循环展开）"""
        stack = [entry]
        while stack:
            current = stack.pop()
            raw_type = current.get("Type")
            if isinstance(raw_type, int):
                current["Type"] = ENTRY_TYPE_MAP.get(raw_type, "regular")
            for child in current.get("Children") or []:
                stack.append(child)

    @staticmethod
    def _normalize_summary_paths(entry: dict, basename: str):
        """将 summary 路径标准化为相对路径（去除 basename 前缀）。

        JuiceFS summary() 的根节点 Path 为 basename，子节点逐级拼接。
        此方法去除该前缀，使所有路径相对于输入目录。
        """
        prefix = basename + "/"
        stack = [entry]
        while stack:
            current = stack.pop()
            path = current.get("Path", "")
            if path == basename:
                current["Path"] = "."
            elif path.startswith(prefix):
                current["Path"] = path[len(prefix):]
            for child in current.get("Children") or []:
                stack.append(child)

    def _execute_batch(self, client, batch_input: BatchInput) -> dict:
        """执行批量操作

        Args:
            client: JuiceFS Client 实例
            batch_input: 批量操作输入

        Returns:
            包含所有操作结果的字典
        """
        results = []
        succeeded = 0
        failed = 0

        for item in batch_input.operations:
            try:
                # 解析操作
                try:
                    sub_operation = Operation(item.operation)
                except ValueError:
                    results.append({
                        "operation": item.operation,
                        "success": False,
                        "data": None,
                        "error": f"Unknown operation: {item.operation}",
                    })
                    failed += 1
                    if batch_input.stop_on_error:
                        break
                    continue

                # 不允许嵌套 BATCH
                if sub_operation == Operation.BATCH:
                    results.append({
                        "operation": item.operation,
                        "success": False,
                        "data": None,
                        "error": "Nested BATCH operations are not allowed",
                    })
                    failed += 1
                    if batch_input.stop_on_error:
                        break
                    continue

                # 解析子操作输入
                if sub_operation not in OPERATION_REGISTRY:
                    results.append({
                        "operation": item.operation,
                        "success": False,
                        "data": None,
                        "error": f"Operation not registered: {item.operation}",
                    })
                    failed += 1
                    if batch_input.stop_on_error:
                        break
                    continue

                sub_input_class, _ = OPERATION_REGISTRY[sub_operation]
                try:
                    sub_input = sub_input_class(**dict(zip(
                        sub_input_class.model_fields.keys(),
                        item.args
                    )))
                except Exception as e:
                    results.append({
                        "operation": item.operation,
                        "success": False,
                        "data": None,
                        "error": f"Invalid arguments: {e}",
                    })
                    failed += 1
                    if batch_input.stop_on_error:
                        break
                    continue

                # 执行子操作
                sub_result = self._execute_operation(client, sub_operation, sub_input)
                results.append({
                    "operation": item.operation,
                    "success": True,
                    "data": sub_result,
                    "error": None,
                })
                succeeded += 1

            except Exception as e:
                results.append({
                    "operation": item.operation,
                    "success": False,
                    "data": None,
                    "error": str(e),
                })
                failed += 1
                if batch_input.stop_on_error:
                    break

        return {
            "results": results,
            "total": len(batch_input.operations),
            "succeeded": succeeded,
            "failed": failed,
        }


def create_worker_process(
    worker_id: int,
    task_queue: Queue,
    result_queue: Queue,
    max_tasks: int,
    max_clients: int,
) -> mp.Process:
    """创建工作进程

    Args:
        worker_id: 工作进程 ID
        task_queue: 任务队列
        result_queue: 结果队列
        max_tasks: 最大任务数
        max_clients: 最大 Client 数

    Returns:
        工作进程对象
    """
    worker = JuiceFSWorker(
        task_queue=task_queue,
        result_queue=result_queue,
        worker_id=worker_id,
        max_tasks=max_tasks,
        max_clients=max_clients,
    )
    process = mp.Process(target=worker.run, daemon=True)
    return process