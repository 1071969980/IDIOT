from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from api.agent.session_agent_config.utils import resolve_scope_value
from api.agent.tools.type import UserToolCallingPermissionRole

# scope_def 解析键，按优先级排列。点号分隔表示嵌套路径。
# 工具特定路径优先，回退到通用路径。
FILE_OPS_USER_ID_PATHS: list[str] = ["file_ops_tool.user_id_for_scope", "user_id_for_scope"]
FILE_OPS_ROLE_PATHS: list[str] = ["file_ops_tool.user_permission_role", "user_permission_role"]
FILE_OPS_ALLOWED_DIRS_PATHS: list[str] = ["file_ops_tool.white_list", "allowed_rel_dirs_in_juicefs_for_tool"]


class FileOpsToolScope(BaseModel):
    """文件操作工具的作用域配置。"""

    user_id_for_scope: UUID
    white_list: list[PurePosixPath] = Field(default_factory=list)
    black_list: list[PurePosixPath] = Field(default_factory=list)
    role: UserToolCallingPermissionRole


def resolve_file_ops_scope(
    config: Any,
    scope_def: dict[str, Any],
) -> FileOpsToolScope:
    """解析文件操作工具的 scope。

    优先级：
    1. config.tool_scope 已有（overlay/persistence 恢复）
    2. 从 scope_def 通过 resolve_scope_value 解析
    """
    scope = config.tool_scope

    if scope is None:
        user_id_raw = resolve_scope_value(scope_def, FILE_OPS_USER_ID_PATHS)
        user_id = UUID(user_id_raw) if isinstance(user_id_raw, str) else user_id_raw
        role_raw = resolve_scope_value(scope_def, FILE_OPS_ROLE_PATHS)
        role = UserToolCallingPermissionRole(role_raw) if isinstance(role_raw, str) else role_raw
        wl_raw = resolve_scope_value(scope_def, FILE_OPS_ALLOWED_DIRS_PATHS) or []
        white_list = [PurePosixPath(p) if isinstance(p, str) else p for p in wl_raw]

        scope = FileOpsToolScope(
            user_id_for_scope=user_id,
            white_list=white_list,
            role=role,
        )

    return scope
