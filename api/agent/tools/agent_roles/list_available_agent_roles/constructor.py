from typing import Any
from uuid import UUID

from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from pydantic import ValidationError

from api.agent.tools.type import ToolClosure, ToolTaskResult
from api.agent.tools.agent_roles.utils import init_user_agent_role_definition_folder, list_available_agent_roles

from .config_data_model import (
    GENERATION_TOOL_PARAM,
    TOOL_NAME,
    ListAvailableAgentRolesConfig,
    ListAvailableAgentRolesParamDefine,
)


class ListAvailableAgentRoles:
    """列出可用Agent角色的工具"""

    def __init__(self,
                 config: ListAvailableAgentRolesConfig,
                 user_id: UUID) -> None:
        self.config = config
        self.user_id = user_id

        # 创建并持有存储后端实例
        self._storage_backend = self._create_storage_backend()

    def _create_storage_backend(self):
        """根据配置创建存储后端实例"""
        from ..storage_backend.distributed import DistributedAgentRoleBackend
        from ..storage_backend.local import LocalAgentRoleBackend

        if self.config.storage_backend == "distributed":
            return DistributedAgentRoleBackend(user_id=self.user_id)
        elif self.config.storage_backend == "local":
            return LocalAgentRoleBackend(
                user_id=self.user_id,
                base_path=self.config.local_base_path or "/tmp/agent_role_storage"
            )
        else:
            raise ValueError(f"Unknown storage_backend: {self.config.storage_backend}")

    async def __call__(self, **kwargs: dict[str, Any]) -> ToolTaskResult:
        """
        列出用户可用的所有Agent角色定义

        Args:
            **kwargs: 额外参数（虽然工具定义无参数，但保持兼容性）

        Returns:
            ToolTaskResult: 包含Agent角色列表的执行结果
        """
        # 传入存储后端实例
        role_names = await list_available_agent_roles(self.user_id, self._storage_backend)

        if "User-Delegated Agent" not in role_names:
            await init_user_agent_role_definition_folder(
                self.user_id, "User-Delegated Agent", self._storage_backend
            )
            role_names = await list_available_agent_roles(self.user_id, self._storage_backend)

        if not role_names:
            result_msg = "Does not find any agent role."
        else:
            result_msg = f"Found {len(role_names)} agent role(s):\n"
            for i, role_name in enumerate(role_names, 1):
                result_msg += f"{i}. {role_name}\n"

        return ToolTaskResult(
            str_content=result_msg,
            json_content={
                "role_count": len(role_names),
                "roles": role_names
            },
            occur_error=False
        )

def construct_tool(
    config: ListAvailableAgentRolesConfig,
    **kwargs: dict[str, Any]
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    """
    构造list_available_agent_roles工具

    Args:
        config: 工具配置
        **kwargs: 其他参数，必须包含 user_id

    Returns:
        tuple: (工具参数定义, 工具实例)
    """
    user_id: UUID | None = kwargs.get("user_id") # type: ignore

    if user_id is None:
        raise ValueError("user_id is required")

    tool = ListAvailableAgentRoles(config, user_id)

    return (
        GENERATION_TOOL_PARAM,
        tool,
    )


CONSTRUCTOR = {TOOL_NAME: construct_tool}