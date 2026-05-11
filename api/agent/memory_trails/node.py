from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam

if TYPE_CHECKING:
    from api.agent.tools.data_model import ToolTaskResult


@dataclass
class MemoryNode:
    """记忆树节点，以链表范式组织。

    节点不持有其他节点的引用，树的组织完全依赖 ID。
    prev_id 指向前驱节点，构成链表方向。
    """

    id: UUID
    content: ChatCompletionMessageParam
    prev_id: UUID | None = None
    is_new: bool = False
    is_context_breakpoint: bool = False
    tool_task_result: "ToolTaskResult | None" = None
    tool_name: str | None = None
    to_agent_msg: bool = False

    def to_dict(self) -> dict:
        """转换为可 JSON 序列化的字典。"""
        return {
            "id": str(self.id),
            "content": self.content,
            "prev_id": str(self.prev_id) if self.prev_id else None,
            "tool_name": self.tool_name,
            "to_agent_msg": self.to_agent_msg,
        }
