# api/agent/tools/sub_agent/submit_result_constructor.py

"""submit_result 工具的动态构造。"""

from dataclasses import dataclass

from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

from api.agent.tools.dynamic_tool_DI.constructor import construct_tool
from api.agent.tools.type import ToolClosure
from pydantic import BaseModel, Field


@dataclass
class ResultContainer:
    """submit_result 结果容器。"""

    result: str | None = None
    called: bool = False


class SubmitResultParamDefine(BaseModel):
    """submit_result 工具的参数定义。"""

    result: str = Field(
        ...,
        description="要返回给主 agent 的结果文本"
    )


def construct_submit_result_tool(
    result_container: ResultContainer
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    """构造 submit_result 工具。

    使用动态工具注入和结果容器模式。

    Args:
        result_container: 用于存储结果的可变容器

    Returns:
        (工具参数, 工具闭包) 元组
    """
    async def submit_result_callback(param: BaseModel) -> None:
        if not isinstance(param, SubmitResultParamDefine):
            error_msg = (
                f"Expected SubmitResultParamDefine, got {type(param).__name__}",
            )
            raise TypeError(error_msg)
        if result_container.called:
            raise RuntimeError("submit_result 只能调用一次")
        result_container.result = param.result
        result_container.called = True

    return construct_tool(
        tool_name="submit_result",
        tool_description="提交任务执行结果给主 agent。此工具只能调用一次。",
        tool_param_model=SubmitResultParamDefine,
        call_back=submit_result_callback
    )
