"""用户 Pod 命令执行模块数据模型"""

from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID
from threading import Event


@dataclass
class CommandResult:
    """命令执行结果"""
    stdout: str
    stderr: str
    returncode: Optional[int]
    interrupted: bool = False
    error: Optional[str] = None


@dataclass
class PodCommandSession:
    """Pod 命令会话状态"""
    user_id: UUID
    pod_name: str
    namespace: str
    image: str = ""
    # 多线程信号 Event，用于中断命令执行
    interrupt_event: Event = field(default_factory=Event)
    # 会话是否活跃
    is_active: bool = True
    # 错误信息
    last_error: Optional[str] = None