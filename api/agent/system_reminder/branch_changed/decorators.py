from typing import TYPE_CHECKING, cast
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from openai.types.chat.chat_completion_system_message_param import ChatCompletionSystemMessageParam

from api.agent.life_cycle_decorators import lifecycle_hook
from api.agent.logic_mark_def import TO_REMINDER_BRANCH_CHANGED_MARK_NAME
from api.agent.xml_marks_def import SYS_REMINDER_BLOCK_START, SYS_REMINDER_BLOCK_END

if TYPE_CHECKING:
    from api.agent.base_agent import AgentBase


@lifecycle_hook('on_agent_start', position='before')
async def inject_branch_changed_reminder(
    self: 'AgentBase',
    memories: list[ChatCompletionMessageParam]
):
    from api.agent.strategy.main_agent import MainAgent
    if not hasattr(self, 'session_task') or not callable(getattr(self, 'session_task')):
        return
    if not hasattr(self, 'branch_name'):
        return
    agent = cast('MainAgent', self)
    session_task = await agent.session_task()
    if session_task is None:
        return

    logic_mark = session_task.logic_mark
    if logic_mark is None:
        return
    if not logic_mark.get(TO_REMINDER_BRANCH_CHANGED_MARK_NAME, False):
        return

    reminder_content = _format_branch_changed_reminder(agent.branch_name)

    msg = ChatCompletionSystemMessageParam(
        content=reminder_content,
        role="system"
    )
    self._runtime_memories.append(msg)
    self._new_memories.append(msg)


def _format_branch_changed_reminder(branch_name: str) -> str:
    return (
        f"{SYS_REMINDER_BLOCK_START}\n"
        f"The branch of the current session task has been set to '{branch_name}'. "
        "Please be aware of this branch change when proceeding.\n"
        f"{SYS_REMINDER_BLOCK_END}\n"
    )
