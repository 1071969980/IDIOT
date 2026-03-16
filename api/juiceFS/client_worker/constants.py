"""JuiceFS 客户端工作进程池配置常量"""

from enum import Enum


class Operation(str, Enum):
    """JuiceFS 支持的操作类型

    继承 str 使其可以直接用于字符串比较和 JSON 序列化。
    """
    READ = "read"
    WRITE = "write"
    EXISTS = "exists"
    LISTDIR = "listdir"
    MKDIR = "mkdir"
    MKDIRS = "makedirs"
    REMOVE = "remove"
    RMDIR = "rmdir"
    RENAME = "rename"
    STAT = "stat"
    TRUNCATE = "truncate"
    CHMOD = "chmod"
    GETXATTR = "getxattr"
    SETXATTR = "setxattr"
    LISTXATTR = "listxattr"
    REMOVEXATTR = "removexattr"


# Worker 配置
DEFAULT_NUM_WORKERS = 4  # 默认工作进程数量
DEFAULT_MAX_TASKS_PER_WORKER = 500  # 每个工作进程处理的最大任务数
DEFAULT_MAX_CLIENTS_PER_WORKER = 20  # 每个工作进程缓存的最大 Client 数量

# 任务配置
DEFAULT_TASK_TIMEOUT = 30.0  # 默认任务超时时间（秒）
WORKER_IDLE_TIMEOUT = 60  # Worker 空闲超时时间（秒）
DEFAULT_QUEUE_PUT_TIMEOUT = 5.0  # 队列 put 操作超时时间（秒）