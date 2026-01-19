"""
Agent Role 存储后端模块

提供不同的存储后端实现：
- DistributedAgentRoleBackend: 使用分布式文件系统
- LocalAgentRoleBackend: 使用本地文件系统
"""

from .base import AgentRoleStorageBackend
from .distributed import DistributedAgentRoleBackend
from .local import LocalAgentRoleBackend

__all__ = [
    "AgentRoleStorageBackend",
    "DistributedAgentRoleBackend",
    "LocalAgentRoleBackend"
]
