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
    key_files: list[str] | None = Field(
        default=None,
        description=(
            "重要文件路径列表。压缩后会重新读取这些文件的内容并注入到上下文中，"
            "确保你能继续操作这些文件。仅列出最关键的文件（建议不超过5个）。"
        ),
    )


GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name=TOOL_NAME,
        description=(
            "压缩对话上下文。调用此工具时，提供一段总结文本，该文本将替代之前的所有对话历史。"
            "请在总结中保留关键信息、重要决策和当前任务状态。"
            "系统会在压缩后自动恢复工具启用状态、TODO列表和已加载技能文档。"
            "如果你正在编辑关键文件，可通过 key_files 参数指定文件路径，压缩后系统会自动重新读取并注入其内容。"
        ),
        parameters=turn_pydantic_model_to_json_schema(SummarizationCompactParamDefine),
    ),
)
