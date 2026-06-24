"""用户 Pod 调度器常量定义"""

from api.core.env_config import namespace_config

# K8S 命名空间
K8S_NAMESPACE = namespace_config.k8s_namespace_user_space

# 心跳超时时间（秒）- 超过此时间未收到心跳则卸载 Pod
HEARTBEAT_TIMEOUT_SECONDS = 3600  # 1小时

# Pod 创建超时时间（秒）
POD_CREATION_TIMEOUT_SECONDS = 300  # 5分钟

# Pod 状态检查间隔（秒）
POD_STATUS_CHECK_INTERVAL_SECONDS = 5

# 心跳检查任务间隔（秒）
HEARTBEAT_CHECK_INTERVAL_SECONDS = 60

# 用户 Pod 容器名称
USER_POD_CONTAINER_NAME = "app"

# JuiceFS 挂载路径
JUICEFS_MOUNT_PATH = "/dist_fs"


class PodStatus:
    """Pod 状态枚举"""
    CREATING = "creating"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"