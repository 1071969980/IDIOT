"""
read_file 工具的配置和参数定义
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
TOOL_NAME = "read_file"


class ReadFileConfig(SessionToolConfigBase):
    """
    ReadFile 工具的配置类

    Attributes:
        enabled: 是否启用工具
        storage_backend: 存储后端类型选择
            - "memory": 使用内存存储（测试用）
            - "local": 使用本地文件系统（测试用）
            - "user_space": 使用用户空间文件系统（生产环境）
            - "kwargs_DI": 从依赖注入获取存储后端实例
    """

    enabled: bool = True

    storage_backend: Literal["memory", "local", "user_space", "kwargs_DI", "user_pod"] = Field(
        default="user_pod",
        description=(
            "存储后端类型选择。"
            "'memory' 使用内存存储；"
            "'local' 使用本地文件系统；"
            "'user_space' 使用用户空间文件系统；"
            "'kwargs_DI' 从依赖注入获取存储后端实例；"
            "'user_pod' 在用户 Pod 中执行文件操作。"
        )
    )

    local_base_path: str | None = Field(
        default=None,
        description="本地文件系统的基础路径（仅 storage_backend='local' 时使用）"
    )


class ReadFileParamDefine(BaseModel):
    """
    ReadFile 工具的参数定义

    支持读取文件内容，支持偏移量和行数限制。
    输出自动包含行号，长行会被自动截断。
    """

    file_path: str = Field(
        description="要读取的文件路径。相对于用户工作目录的路径。"
    )
    offset: int | None = Field(
        default=None,
        description=(
            "起始行的偏移量（从0开始）。如果为 None，从文件开头开始读取。"
            "例如，offset=10 表示从第11行开始读取。"
        )
    )
    limit: int | None = Field(
        default=None,
        description=(
            "要读取的最大行数。如果为 None，读取到文件末尾。"
            "例如，limit=100 表示最多读取100行。"
        )
    )

    model_config = ConfigDict(extra='allow')  # 允许额外字段（向前兼容）


# 默认工具配置
DEFAULT_TOOL_CONFIG = {
    TOOL_NAME: ReadFileConfig(
        enabled=True,
        storage_backend="user_pod"
    )
}


# 工具生成参数（用于 LLM Function Calling）
READ_FILE_GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name=TOOL_NAME,
        description=(
            "读取文件内容，支持从指定行开始读取、限制读取行数。"
            "输出自动包含行号，超过1000字符的行会被截断。"
        ),
        parameters=turn_pydantic_model_to_json_schema(ReadFileParamDefine),
        parameters_example={
            "file_path": "src/main.py",
            "offset": 10,
            "limit": 50
        }  # extra fields for tool param example, some llm chat template rendering it.
    )  # type: ignore
)
