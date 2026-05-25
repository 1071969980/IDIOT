"""
list_directory 工具的配置和参数定义
"""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

# 引入项目的基础配置类
from api.agent.tools.config_data_model import (
    SessionToolConfigBase,
    turn_pydantic_model_to_json_schema
)
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition

# 工具名称
TOOL_NAME = "list_directory"


class ListDirectoryConfig(SessionToolConfigBase):
    """
    ListDirectory 工具的配置类

    Attributes:
        enabled: 是否启用工具
        storage_backend: 存储后端类型选择
            - "juicefs_sdk": 使用 JuiceFS SDK（推荐）
            - "kwargs_DI": 从依赖注入获取存储后端实例
    """

    enabled: bool = True
    explicit: bool = True
    storage_backend: Literal["kwargs_DI", "juicefs_sdk"] = Field(
        default="juicefs_sdk",
        description=(
            "存储后端类型选择。"
            "'juicefs_sdk' 使用 JuiceFS SDK 直接操作文件系统（推荐）；"
            "'kwargs_DI' 从依赖注入获取存储后端实例。"
        )
    )


class ListDirectoryParamDefine(BaseModel):
    """
    ListDirectory 工具的参数定义

    支持列出目录内容。
    """

    directory_path: str = Field(
        description="要列出的目录路径。相对于用户工作目录的路径。如果为空字符串或 None，则列出根目录。"
    )

    model_config = ConfigDict(extra='allow')  # 允许额外字段（向前兼容）


# 默认工具配置
DEFAULT_TOOL_CONFIG = {
    TOOL_NAME: ListDirectoryConfig(
        enabled=True,
        explicit=True,
        storage_backend="juicefs_sdk"
    )
}


# 工具生成参数（用于 LLM Function Calling）
LIST_DIRECTORY_GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name=TOOL_NAME,
        description=(
            "列出目录内容。"
            "返回目录下的文件和子目录列表。"
        ),
        parameters=turn_pydantic_model_to_json_schema(ListDirectoryParamDefine),
        parameters_example={
            "directory_path": "src/"
        }  # extra fields for tool param example, some llm chat template rendering it.
    )  # type: ignore
)