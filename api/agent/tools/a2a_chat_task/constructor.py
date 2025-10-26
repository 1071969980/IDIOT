from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

from api.agent.tools.type import ToolClosure

from .config_data_model import TOOL_NAME, CreateChatTaskToAnotherAgentConfig
from typing import Any

def construct_tool(
    config: CreateChatTaskToAnotherAgentConfig,
    **kwargs: dict[str, Any]
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    pass


CONSTRUCTOR = {TOOL_NAME: construct_tool}
