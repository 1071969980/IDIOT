"""用户 Pod 命令执行模块异常"""


class UserPodCommandError(Exception):
    """基础异常"""
    pass


class PodNotReadyError(UserPodCommandError):
    """Pod 未就绪"""
    pass


class PodCreationTimeoutError(UserPodCommandError):
    """Pod 创建超时"""
    pass


class PodStatusAbnormalError(UserPodCommandError):
    """Pod 状态异常"""
    pass


class SessionTimeoutError(UserPodCommandError):
    """会话超时"""
    pass


class CommandExecutionError(UserPodCommandError):
    """命令执行错误"""
    pass


class CommandInterruptedError(UserPodCommandError):
    """命令被中断"""
    pass


class SchedulerServiceError(UserPodCommandError):
    """调度器服务错误"""
    pass