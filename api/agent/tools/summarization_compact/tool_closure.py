from typing import Any

from pydantic import ValidationError
from openai.types.chat.chat_completion_user_message_param import (
    ChatCompletionUserMessageParam,
)

from api.agent.memory_tree.tree import MemoryTree
from api.agent.tools.data_model import ToolTaskResult
from api.agent.tools.type import ToolClosure

from .config_data_model import TOOL_NAME, SummarizationCompactParamDefine


def make_summarization_compact_closure(
    memory_tree: MemoryTree,
    tool_choice_steering: set[str],
    branch_name: str,
) -> ToolClosure:
    """动态构造 summarization_compact 工具闭包，捕获运行时依赖。

    Args:
        memory_tree: 运行时记忆树，用于添加压缩后的总结消息
        tool_choice_steering: 工具选择引导集合，执行后从中移除自身
        branch_name: 当前运行的分支名
    """

    async def closure(**kwargs: dict[str, Any]) -> ToolTaskResult:
        try:
            param = SummarizationCompactParamDefine.model_validate(kwargs)
        except ValidationError as e:
            error_msg = "\n".join([error["msg"] for error in e.errors()])
            return ToolTaskResult(
                str_content=f"参数验证失败：\n{error_msg}",
                occur_error=True,
            )

        # 1. 添加 user 消息到对应分支，标记为 context_breakpoint
        memory_tree.append_to_branch(
            branch_name,
            ChatCompletionUserMessageParam(role="user", content=param.summary),
            is_new=True,
            to_agent_msg=False,
            is_context_breakpoint=True,
        )

        # 2. 从 tool_choice_steering 移除自身
        tool_choice_steering.discard(TOOL_NAME)

        return ToolTaskResult(str_content="上下文压缩成功。请继续执行当前任务。")

    return closure
