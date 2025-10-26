from uuid import UUID

from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

from api.agent.tools.config_data_model import SessionToolConfigBase
from api.agent.tools.type import ToolClosure
from .tool_init_function import TOOL_INIT_FUNCTIONS


class ToolFactory:

    def __init__(self,
                user_id: UUID,
                session_id: UUID,
                session_task_id: UUID):
        self.user_id = user_id
        self.session_id = session_id
        self.session_task_id = session_task_id

    async def prerare_tool(self, tool_name: str,
                            config: SessionToolConfigBase,
                            ) -> tuple[ChatCompletionToolParam, ToolClosure]:
        if tool_name not in TOOL_INIT_FUNCTIONS.keys():
            raise ValueError(f"Tool {tool_name} is not available")
        
        return await TOOL_INIT_FUNCTIONS[tool_name](
            config = config,
            kwargs={
                "user_id": self.user_id,
                "session_id": self.session_id,
                "session_task_id": self.session_task_id
            }
        )
        
