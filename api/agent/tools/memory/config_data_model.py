from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from api.agent.session_agent_config.utils import resolve_scope_value
from api.agent.tools.file_operations.config_scope_data_model import FileOpsToolScope
from api.agent.tools.type import UserToolCallingPermissionRole

MEMORY_USER_ID_PATHS: list[str] = [
    "memory_tool.user_id_for_scope",
    "user_id_for_scope",
]
MEMORY_ROLE_PATHS: list[str] = [
    "memory_tool.user_permission_role",
    "user_permission_role",
]
MEMORY_DIRS_PATHS: list[str] = [
    "memory_tool.memory_dirs",
    "allowed_rel_dirs_in_juicefs_for_tool",
]


class MemoryToolScope(BaseModel):
    """记忆 Agent 专用作用域模型。"""

    user_id_for_scope: UUID
    memory_dirs: list[PurePosixPath] = Field(default_factory=list)
    role: UserToolCallingPermissionRole

    def to_file_ops_scope(self) -> FileOpsToolScope:
        """转换为 FileOpsToolScope, 用于构造 JuiceFSSdkBackend。"""
        return FileOpsToolScope(
            user_id_for_scope=self.user_id_for_scope,
            white_list=self.memory_dirs,
            black_list=[],
            role=self.role,
        )


def resolve_memory_scope(scope_def: dict[str, Any]) -> MemoryToolScope:
    """从 scope_def 解析记忆工具的 scope。"""
    user_id_raw = resolve_scope_value(scope_def, MEMORY_USER_ID_PATHS)
    user_id = UUID(user_id_raw) if isinstance(user_id_raw, str) else user_id_raw
    role_raw = resolve_scope_value(scope_def, MEMORY_ROLE_PATHS)
    role = (
        UserToolCallingPermissionRole(role_raw)
        if isinstance(role_raw, str) else role_raw
    )
    dirs_raw = resolve_scope_value(scope_def, MEMORY_DIRS_PATHS) or []
    memory_dirs = [
        PurePosixPath(p) if isinstance(p, str) else p
        for p in dirs_raw
    ]

    return MemoryToolScope(
        user_id_for_scope=user_id,
        memory_dirs=memory_dirs,
        role=role,
    )
