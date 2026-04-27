from typing import TYPE_CHECKING, cast, assert_type
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from openai.types.chat.chat_completion_system_message_param import ChatCompletionSystemMessageParam
from openai.types.chat.chat_completion_user_message_param import ChatCompletionUserMessageParam

from api.agent.life_cycle_decorators import lifecycle_hook
from api.agent.logic_mark_def import TO_REMINDER_TOOL_ENABLE_STATUS_MARK_NAME, TO_REMINDER_MCP_SERVER_CONFIG_CHANGED_MARK_NAME
from api.agent.xml_marks_def import SYS_REMINDER_BLOCK_START, SYS_REMINDER_BLOCK_END, TOOL_DISCOVERY_RESULT_BLOCK_START

if TYPE_CHECKING:
    from api.agent.base_agent import AgentBase


@lifecycle_hook('on_agent_start', position='before')
async def inject_tool_enable_status_reminder(
    self: 'AgentBase',
    branch_name: str
):
    from api.agent.strategy.main_agent import MainAgent
    # assert has session task getter
    if not hasattr(self, 'session_task') or not callable(getattr(self, 'session_task')):
        return
    agent = cast('MainAgent', self)
    session_task = await agent.session_task()
    if session_task is None:
        return

    logic_mark = session_task.logic_mark
    if logic_mark is None:
        return
    if not logic_mark.get(TO_REMINDER_TOOL_ENABLE_STATUS_MARK_NAME, False):
        return

    reminder_content = _format_tool_enable_status_reminder(agent.enable_explicit_tools_name)

    msg = ChatCompletionSystemMessageParam(
        content=reminder_content,
        role="system"
    )
    self._memory_tree.append_to_branch(branch_name, msg)

@lifecycle_hook('on_agent_start', position='before')
async def inject_mcp_server_config_changed_reminder(
    self: 'AgentBase',
    branch_name: str
):
    from api.agent.strategy.main_agent import MainAgent
    # assert has session task getter
    if not hasattr(self, 'session_task') or not callable(getattr(self, 'session_task')):
        return
    agent = cast('MainAgent', self)
    session_task = await agent.session_task()
    if session_task is None:
        return

    logic_mark = session_task.logic_mark
    if logic_mark is None:
        return
    if not logic_mark.get(TO_REMINDER_MCP_SERVER_CONFIG_CHANGED_MARK_NAME, False):
        return

    reminder_content = _format_mcp_server_config_changed_reminder()

    msg = ChatCompletionSystemMessageParam(
        content=reminder_content,
        role="system"
    )
    self._memory_tree.append_to_branch(branch_name, msg)


def _format_mcp_server_config_changed_reminder() -> str:
    return (
        f"{SYS_REMINDER_BLOCK_START}\n"
        "MCP server configuration has been changed since your last run. "
        "The available MCP tools may have been added, removed, or modified. "
        "You could re-discover available tools using the tool_discovery tool to get the latest tool list.\n"
        f"{SYS_REMINDER_BLOCK_END}\n"
    )


def _format_tool_enable_status_reminder(enable_explicit_tools_name: set[str]) -> str:
    return (
        f"{SYS_REMINDER_BLOCK_START}\n"
        "Following tool_name are the explicit tools that you are allowed to use:\n"
        f"{',\n\t- '.join(enable_explicit_tools_name)}\n"
        f"Also, you are also allowed to use the implicit tools discovered by the tool_discovery tool which contains in the {TOOL_DISCOVERY_RESULT_BLOCK_START} xml mark.\n"
        "IMPORTANT: Calls to any tools not explicitly allowed will be REJECTED.\n"
        f"{SYS_REMINDER_BLOCK_END}\n"
    )