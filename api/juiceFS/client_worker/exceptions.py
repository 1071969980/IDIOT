"""JuiceFS 客户端工作进程池异常定义"""


class WorkerPoolError(Exception):
    """工作进程池基础异常"""
    pass


class WorkerPoolNotInitializedError(WorkerPoolError):
    """工作进程池未初始化"""
    pass


class WorkerPoolAlreadyRunningError(WorkerPoolError):
    """工作进程池已在运行"""
    pass


class TaskTimeoutError(WorkerPoolError):
    """任务超时"""
    pass


class TaskExecutionError(WorkerPoolError):
    """任务执行错误"""

    def __init__(self, message: str, task_id: str):
        super().__init__(message)
        self.task_id = task_id


class TaskCancelledError(WorkerPoolError):
    """任务被取消（cancel_event 触发）"""

    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__(f"Task {task_id} cancelled")


class UnsupportedOperationError(WorkerPoolError):
    """不支持的操作"""
    pass