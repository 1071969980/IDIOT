import inspect
from uuid import UUID

from typing import Any

from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

from api.agent.tools.config_data_model import SessionToolConfigBase
from api.agent.tools.type import ToolClosure
from .tool_init_function import TOOL_INIT_FUNCTIONS

class ToolFactory:

    def __init__(self,
                user_id: UUID,
                session_id: UUID,
                session_task_id: UUID,
                branch_name: str,
                llm_service_name: str,
                scope_def: dict[str, Any],
                **kwargs: Any):
        self.user_id = user_id
        self.session_id = session_id
        self.session_task_id = session_task_id
        self.branch_name = branch_name
        self.llm_service_name = llm_service_name
        self.scope_def = scope_def
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
                user_id=self.user_id,
                session_id=self.session_id,
                session_task_id=self.session_task_id,
                branch_name=self.branch_name,
                llm_service_name=self.llm_service_name,
                scope_def=self.scope_def,
                **self.kwargs
            )
        else:
            # 同步构造函数
            return init_func(
                config=config,
                user_id=self.user_id,
                session_id=self.session_id,
                session_task_id=self.session_task_id,
                branch_name=self.branch_name,
                llm_service_name=self.llm_service_name,
                scope_def=self.scope_def,
                **self.kwargs
            ) # type: ignore