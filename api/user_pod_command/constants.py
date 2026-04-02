"""用户 Pod 命令执行模块常量定义"""

# 心跳间隔（秒）
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 30.0

# 状态检查间隔（秒）
DEFAULT_STATUS_CHECK_INTERVAL_SECONDS = 10.0

# 默认会话超时时间（秒）
DEFAULT_SESSION_TIMEOUT_SECONDS = 3600.0  # 1小时

# Pod 就绪等待超时（秒）
DEFAULT_POD_READY_TIMEOUT_SECONDS = 300.0  # 5分钟

# 命令执行轮询间隔（秒）
COMMAND_POLL_INTERVAL_SECONDS = 5  # 5s

# WebSocket 通道
STDOUT_CHANNEL = 1
STDERR_CHANNEL = 2  # kubernetes stream 中 stderr 使用 channel 2

# 中断信号
INTERRUPT_SIGINT = b'\x03'  # Ctrl+C

# user_pod_scheduler 服务地址
SCHEDULER_SERVICE_URL = "http://user-pod-scheduler:8001"