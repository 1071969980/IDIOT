from collections.abc import Callable, Awaitable
from typing import Union

from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

from api.agent.tools.type import ToolClosure

# 工具初始化函数类型：可以是同步或异步函数
ToolInitFunction = Union[
    Callable[..., tuple[ChatCompletionToolParam, ToolClosure]],
    Callable[..., Awaitable[tuple[ChatCompletionToolParam, ToolClosure]]]
]
from api.agent.tools.ask_user.constructor import CONSTRUCTOR as ASK_USER_CONSTRUCTOR
from api.agent.tools.todo.constructor import CONSTRUCTOR as TODO_WRITE_CONSTRUCTOR
from api.agent.tools.file_operations.read_file.constructor import CONSTRUCTOR as READ_FILE_CONSTRUCTOR
from api.agent.tools.file_operations.edit_file.constructor import CONSTRUCTOR as EDIT_FILE_CONSTRUCTOR
from api.agent.tools.file_operations.write_file.constructor import CONSTRUCTOR as WRITE_FILE_CONSTRUCTOR
from api.agent.tools.file_operations.list_directory.constructor import CONSTRUCTOR as LIST_DIRECTORY_CONSTRUCTOR
from api.agent.tools.file_operations.move_file.constructor import CONSTRUCTOR as MOVE_FILE_CONSTRUCTOR
from api.agent.tools.file_operations.copy_file.constructor import CONSTRUCTOR as COPY_FILE_CONSTRUCTOR
from api.agent.tools.file_operations.delete_file.constructor import CONSTRUCTOR as DELETE_FILE_CONSTRUCTOR
from api.agent.tools.sub_agent.constructor import CONSTRUCTOR as SUB_AGENT_CONSTRUCTOR
from api.agent.tools.bash.constructor import CONSTRUCTOR as BASH_CONSTRUCTOR
from api.agent.tools.skills.load_skill.constructor import CONSTRUCTOR as LOAD_SKILL_CONSTRUCTOR
from api.agent.tools.skills.skill_advisor.constructor import CONSTRUCTOR as SKILL_ADVISOR_CONSTRUCTOR

TOOL_INIT_FUNCTIONS: dict[str, ToolInitFunction] = {
    **ASK_USER_CONSTRUCTOR,
    **TODO_WRITE_CONSTRUCTOR,
    **READ_FILE_CONSTRUCTOR,
    **EDIT_FILE_CONSTRUCTOR,
    **WRITE_FILE_CONSTRUCTOR,
    **LIST_DIRECTORY_CONSTRUCTOR,
    **MOVE_FILE_CONSTRUCTOR,
    **COPY_FILE_CONSTRUCTOR,
    **DELETE_FILE_CONSTRUCTOR,
    **SUB_AGENT_CONSTRUCTOR,
    **BASH_CONSTRUCTOR,
    **LOAD_SKILL_CONSTRUCTOR,
    **SKILL_ADVISOR_CONSTRUCTOR,
}
