"""
edit_file 工具的配置和参数定义
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
TOOL_NAME = "edit_file"


class EditFileConfig(SessionToolConfigBase):
    """
    EditFile 工具的配置类

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


class EditFileParamDefine(BaseModel):
    """
    EditFile 工具的参数定义

    支持编辑文件内容，通过替换指定字符串实现。
    """

    file_path: str = Field(
        description="要编辑的文件路径。相对于用户工作目录的路径。"
    )
    old_string: str = Field(
        description="要替换的字符串。必须精确匹配，不支持正则表达式。"
    )
    new_string: str = Field(
        description="替换后的字符串。"
    )
    replace_all: bool = Field(
        default=False,
        description=(
            "是否替换所有匹配项。如果为 False，且 old_string 在文件中出现多次，"
            "则返回错误要求用户确认。如果为 True，替换所有匹配项。"
        )
    )

    model_config = ConfigDict(extra='allow')  # 允许额外字段（向前兼容）


# 默认工具配置
DEFAULT_TOOL_CONFIG = {
    TOOL_NAME: EditFileConfig(
        enabled=True,
        explicit=True,
        storage_backend="juicefs_sdk"
    )
}


# 工具生成参数（用于 LLM Function Calling）
EDIT_FILE_GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name=TOOL_NAME,
        description="编辑文件内容，通过替换指定的字符串实现。支持单次替换或全局替换。",
        parameters=turn_pydantic_model_to_json_schema(EditFileParamDefine),
        parameters_example={
            "file_path": "src/main.py",
            "old_string": "def hello_world():",
            "new_string": "def hello_universe():",
            "replace_all": False
        }  # extra fields for tool param example, some llm chat template rendering it.
    )  # type: ignore
)
