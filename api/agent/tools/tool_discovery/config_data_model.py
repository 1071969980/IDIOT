"""
tool_discovery 工具不通过工具工厂进行注册和实例化。和一般的工具不同。
它在 agent 初始化其他工具之后，通过一个较独立的函数进行实例化，最终提供给 agent 使用。
"""
from typing import Literal
from api.agent.tools.config_data_model import SessionToolConfigBase
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition

from pydantic import BaseModel, ConfigDict, Field, model_validator, ValidationError
from api.agent.tools.config_data_model import turn_pydantic_model_to_json_schema

TOOL_NAME = "tool_discovery"

TOOL_DESCRIPTION = """
搜索或查看暂未披露的，但是已被加载并可用的工具。MCP 服务提供的工具默认处于隐藏状态。
当用户暗示你可以使用某些功能但是你尚不知情时，可以尝试使用 tool_discovery 工具。
"""

class ToolDiscoveryToolParamDefine(BaseModel):
    action: Literal["search", "reveal"] = Field(
        description=(
            "要执行的操作类型：'search'（搜索）或 'reveal'（显示）：\n"
            "search: 搜索工具，支持 grep 模式和 bm25 模式的搜索，返回工具的名称和描述。\n"
            'Result format: 每个匹配工具信息按 markdown 列表项返回。形如 " *工具名称*: *工具描述...(可能被截断)* "'
            "reveal: 显示工具，返回工具的完整信息，json 格式的字符串。\n"
            'Result format: 每个工具的完整信息每一条以 <tool_discovery>{"description": "...", "name": "...", "parameters": {...}}</tool_discovery> 单行 json 格式的字符串返回，被包裹在 <tool_discovery> 标签中。'
        )
    )
    mode: Literal["grep", "bm25"] | None = Field(
        description=(
            "搜索模式：'grep'（grep 模式）或 'bm25'（bm25 模式）。"
            "当 action 为 search时有效。\n"
            "grep 模式：使用query中的正则表达式搜索工具的名称和描述，返回匹配到的工具名称和描述。\n"
            "bm25 模式：使用query使用bm25方法搜索工具名称和描述，返回匹配到的工具名称和描述）。\n"
        )
    )
    limit: int | None = Field(
        default=5,
        ge=1,
        description=(
            "返回结果的数量限制。"
            "当 action 为 search 时有效。输入 null 表示返回所有结果。"
        )
    )
    regex: str | None = Field(
        description=(
            "当 action 为 search ，模式为 grep 时有效。内容为正则表达式。:\n"
            '特殊用法：使用 `[\s\S]*` ，配合 "limit": null 列出所有工具'
        )
    )
    query: str | None = Field(
        description=(
            "当 action 为 search ，模式为 bm25 时有效。内容为查询字符串。"
        )
    )
    tool_name: list[str] | None = Field(
        description=(
            "字符串列表。当 action 为 reveal 时有效。内容为精确的工具名称。"
        )
    )
    
    @model_validator(mode="after")
    def validate_action(self):
        if self.action == "search":
            if self.mode is None:
                raise ValidationError("'mode' parameter is required when action is search")
            if self.mode == "grep" and self.regex is None:
                raise ValidationError("'regex' parameter is required when mode is grep")
            if self.mode == "bm25" and self.query is None:
                raise ValidationError("'query' parameter is required when mode is bm25")
        if self.action == "reveal" and self.tool_name is None:
            raise ValidationError("'tool_name' parameter is required when action is reveal")
        return self
