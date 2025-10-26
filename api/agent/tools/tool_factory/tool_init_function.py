from collections.abc import Callable

from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

from api.agent.tools.type import ToolClosure
from api.agent.tools.a2a_chat_task.constructor import CONSTRUCTOR as A2A_CHAT_TASK_CONSTRUCTOR

TOOL_INIT_FUNCTIONS: dict[str, Callable[..., tuple[ChatCompletionToolParam, ToolClosure]]] = {
    **A2A_CHAT_TASK_CONSTRUCTOR,
}
