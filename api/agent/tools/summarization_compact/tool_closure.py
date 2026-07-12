import asyncio
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

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
        # 在 Pydantic 验证前提取 cancel_event（extra='ignore' 会丢弃它）
        cancel_event = cast(asyncio.Event | None, kwargs.get("cancel_event"))

        # 回滚 savepoint：None 表示尚未设置（不可回滚）
        savepoint: UUID | None = None

        try:
            # ---- 入口 fast-return：工作开始前取消 ----
            if cancel_event is not None and cancel_event.is_set():
                return ToolTaskResult(
                    str_content="上下文压缩已被用户取消",
                    occur_error=True,
                )

            # ---- 参数验证 ----
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

            # ---- 记录 savepoint ----
            # 在生命周期钩子注入的 "compact instruction" 消息之后、
            # 第一个工具创建的节点之前。后续取消/异常时回滚到此。
            savepoint = memory_trails._require_marker(marker_name)

            # ---- B1: context_breakpoint + summary ----
            memory_trails.append_to_marker(
                marker_name,
                ChatCompletionUserMessageParam(role="user", content=param.summary),
                is_new=True,
                to_agent_msg=False,
                is_context_breakpoint=True,
            )

            # B1 后取消 → 回滚断点
            if cancel_event is not None and cancel_event.is_set():
                memory_trails.rollback_marker(marker_name, savepoint)
                return ToolTaskResult(
                    str_content="上下文压缩已被用户取消",
                    occur_error=True,
                )

            # ---- B3a-B3d: 状态收集 ----
            from .state_collector import collect_and_inject_post_compression_state

            await collect_and_inject_post_compression_state(
                agent, memory_trails, marker_name, param.key_files,
                cancel_event=cancel_event,
            )

            # 状态收集后取消 → 回滚所有注入节点
            if cancel_event is not None and cancel_event.is_set():
                memory_trails.rollback_marker(marker_name, savepoint)
                return ToolTaskResult(
                    str_content="上下文压缩已被用户取消",
                    occur_error=True,
                )

            # ---- 成功 ----
            return ToolTaskResult(str_content="上下文压缩成功。请继续执行当前任务。")

        except Exception:
            # 异常时回滚已注入节点，然后上抛
            if savepoint is not None:
                memory_trails.rollback_marker(marker_name, savepoint)
            raise

        finally:
            # 所有退出路径统一清理 steering
            tool_choice_steering.discard(TOOL_NAME)
            agent._tool_steering_block_stop = False

    return closure
