"""
write_file 工具的配置和参数定义
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
TOOL_NAME = "write_file"


class WriteFileConfig(SessionToolConfigBase):
    """
    WriteFile 工具的配置类

    Attributes:
        enabled: 是否启用工具
        storage_backend: 存储后端类型选择
            - "juicefs_sdk": 使用 JuiceFS SDK（推荐）
            - "kwargs_DI": 从依赖注入获取存储后端实例
    """

    enabled: bool = True

    storage_backend: Literal["kwargs_DI", "juicefs_sdk"] = Field(
        default="juicefs_sdk",
        description=(
            "存储后端类型选择。"
            "'juicefs_sdk' 使用 JuiceFS SDK 直接操作文件系统（推荐）；"
            "'kwargs_DI' 从依赖注入获取存储后端实例。"
        )
    )


class WriteFileParamDefine(BaseModel):
    """
    WriteFile 工具的参数定义

    支持写入文件内容，可以创建新文件或覆盖现有文件。
    """

    file_path: str = Field(
        description="要写入的文件路径。相对于用户工作目录的路径。"
    )
    content: str = Field(
        description="要写入文件的内容。"
    )
    mode: Literal["create", "overwrite"] = Field(
        default="create",
        description=(
            "写入模式。"
            "'create': 仅创建新文件，如果文件已存在则返回错误。"
            "'overwrite': 允许覆盖现有文件。"
        )
    )

    model_config = ConfigDict(extra='allow')  # 允许额外字段（向前兼容）


# 默认工具配置
DEFAULT_TOOL_CONFIG = {
    TOOL_NAME: WriteFileConfig(
        enabled=True,
        storage_backend="juicefs_sdk"
    )
}


# 工具生成参数（用于 LLM Function Calling）
WRITE_FILE_GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name=TOOL_NAME,
        description="向指定文件写入内容。支持创建新文件或覆盖现有文件。",
        parameters=turn_pydantic_model_to_json_schema(WriteFileParamDefine),
        parameters_example={
            "file_path": "src/new_file.py",
            "content": "def hello():\n    print('Hello, World!')\n",
            "mode": "create"
        }  # extra fields for tool param example, some llm chat template rendering it.
    )  # type: ignore
)
