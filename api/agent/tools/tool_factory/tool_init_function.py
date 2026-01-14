from collections.abc import Callable

from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

from api.agent.tools.type import ToolClosure
from api.agent.tools.a2a_chat_task.constructor import CONSTRUCTOR as A2A_CHAT_TASK_CONSTRUCTOR
from api.agent.tools.ask_user.constructor import CONSTRUCTOR as ASK_USER_CONSTRUCTOR
from api.agent.tools.todo.constructor import CONSTRUCTOR as TODO_WRITE_CONSTRUCTOR
from api.agent.tools.file_operations.read_file.constructor import CONSTRUCTOR as READ_FILE_CONSTRUCTOR
from api.agent.tools.file_operations.edit_file.constructor import CONSTRUCTOR as EDIT_FILE_CONSTRUCTOR
from api.agent.tools.file_operations.write_file.constructor import CONSTRUCTOR as WRITE_FILE_CONSTRUCTOR

TOOL_INIT_FUNCTIONS: dict[str, Callable[..., tuple[ChatCompletionToolParam, ToolClosure]]] = {
    **A2A_CHAT_TASK_CONSTRUCTOR,
    **ASK_USER_CONSTRUCTOR,
    **TODO_WRITE_CONSTRUCTOR,
    **READ_FILE_CONSTRUCTOR,
    **EDIT_FILE_CONSTRUCTOR,
    **WRITE_FILE_CONSTRUCTOR
}
