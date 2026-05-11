from typing import TYPE_CHECKING, Any

from pydantic import ValidationError
from openai.types.chat.chat_completion_user_message_param import (
    ChatCompletionUserMessageParam,
)

from api.agent.memory_trails.trails import MemoryTrails
from api.agent.tools.data_model import ToolTaskResult
from api.agent.tools.type import ToolClosure

from .config_data_model import TOOL_NAME, SummarizationCompactParamDefine

if TYPE_CHECKING:
    from api.agent.base_agent import AgentBase


def make_summarization_compact_closure(
    memory_trails: MemoryTrails,
    tool_choice_steering: set[str],
    marker_name: str,
    agent: "AgentBase",
) -> ToolClosure:
    """动态构造 summarization_compact 工具闭包，捕获运行时依赖。

    Args:
        memory_trails: 运行时记忆路径集，用于添加压缩后的总结消息
        tool_choice_steering: 工具选择引导集合，执行后从中移除自身
        marker_name: 当前运行的标记名
        agent: Agent 实例，用于收集压缩后需要恢复的运行时状态
    """

    async def closure(**kwargs: dict[str, Any]) -> ToolTaskResult:
        try:
            param = SummarizationCompactParamDefine.model_validate(kwargs)
        except ValidationError as e:
            error_msg = "\n".join(
                f"{'.'.join(str(l) for l in err['loc'])} - {err['msg']}"
                for err in e.errors()
            )
            return ToolTaskResult(
                str_content=f"参数验证失败:\n{error_msg}",
                occur_error=True,
            )

        # 1. 添加 user 消息到对应标记，标记为 context_breakpoint
        memory_trails.append_to_marker(
            marker_name,
            ChatCompletionUserMessageParam(role="user", content=param.summary),
            is_new=True,
            to_agent_msg=False,
            is_context_breakpoint=True,
        )

        # 2. 收集并注入运行时状态（工具状态、TODO、技能、关键文件）
        from .state_collector import collect_and_inject_post_compression_state

        await collect_and_inject_post_compression_state(
            agent, memory_trails, marker_name, param.key_files
        )

        # 3. 从 tool_choice_steering 移除自身，解除循环阻止
        tool_choice_steering.discard(TOOL_NAME)
        agent._tool_steering_block_stop = False

        return ToolTaskResult(str_content="上下文压缩成功。请继续执行当前任务。")

    return closure
