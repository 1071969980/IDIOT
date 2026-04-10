import inspect
from uuid import UUID

from typing import Any, Literal
from enum import Enum

from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

from api.agent.tools.config_data_model import SessionToolConfigBase
from api.agent.tools.type import ToolClosure
from .tool_init_function import TOOL_INIT_FUNCTIONS


class UserToolCallingPermissionRole(str, Enum):
    OWNER = "owner"
    VISITOR = "visitor"
    VISITOR_AGENT = "visitor_agent"

class ToolFactory:

    def __init__(self,
                user_id_for_scope: UUID,
                session_id: UUID,
                session_task_id: UUID,
                user_permission_role: UserToolCallingPermissionRole,
                **kwargs: Any):
        self.user_id_for_scope = user_id_for_scope
        self.session_id = session_id
        self.session_task_id = session_task_id
        self.user_permission_role = user_permission_role
        self.kwargs = kwargs

    async def prepare_tool(self, tool_name: str,
                           config: SessionToolConfigBase,
                           ) -> tuple[ChatCompletionToolParam, ToolClosure]:
        if tool_name not in TOOL_INIT_FUNCTIONS.keys():
            raise ValueError(f"Tool {tool_name} is not available")

        init_func = TOOL_INIT_FUNCTIONS[tool_name]

        # 检查是否为异步函数
        if inspect.iscoroutinefunction(init_func):
            # 异步构造函数（如 sub_agent）
            return await init_func(
                config=config,
                user_id_for_scope=self.user_id_for_scope,
                session_id=self.session_id,
                session_task_id=self.session_task_id,
                user_permission_role=self.user_permission_role,
                **self.kwargs
            )
        else:
            # 同步构造函数
            return init_func(
                config=config,
                user_id_for_scope=self.user_id_for_scope,
                session_id=self.session_id,
                session_task_id=self.session_task_id,
                user_permission_role=self.user_permission_role,
                **self.kwargs
            ) # type: ignore
        
