from pydantic import BaseModel, Field
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition

from api.agent.tools.config_data_model import turn_pydantic_model_to_json_schema

TOOL_NAME = "summarization_compact"


class SummarizationCompactParamDefine(BaseModel):
    summary: str = Field(
        ...,
        description="对之前所有对话上下文的总结。压缩后的文本将替代之前的对话历史。",
    )


GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name=TOOL_NAME,
        description=(
            "压缩对话上下文。调用此工具时，提供一段总结文本，该文本将替代之前的所有对话历史。"
            "请在总结中保留关键信息、重要决策和当前任务状态。"
        ),
        parameters=turn_pydantic_model_to_json_schema(SummarizationCompactParamDefine),
    ),
)
