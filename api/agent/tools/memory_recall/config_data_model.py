"""memory_recall 工具的参数定义"""

from pydantic import BaseModel, Field
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition

from api.agent.tools.config_data_model import turn_pydantic_model_to_json_schema

TOOL_NAME = "return_memory_recall"


class ReturnMemoryRecallParamDefine(BaseModel):
    target_marker: str = Field(
        default="major",
        description="目标 Marker 名称，召回结果将追加到此 Marker",
    )
    mem_files: list[str] = Field(
        ...,
        description="需要召回的记忆文件绝对路径列表",
    )
    additional_msg: str | None = Field(
        default=None,
        description="附加说明文本，可补充召回理由或上下文",
    )


GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name=TOOL_NAME,
        description=(
            "将检索到的记忆文件内容召回并注入到指定 Marker。"
            "读取 mem_files 中每个文件的内容，用 <memory_recall> 标记包裹后推送到目标 Marker。"
        ),
        parameters=turn_pydantic_model_to_json_schema(ReturnMemoryRecallParamDefine),
    ),
)
