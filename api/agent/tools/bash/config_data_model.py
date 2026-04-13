"""
bash 工具的配置和参数定义
"""

from pydantic import BaseModel, ConfigDict, Field

from api.agent.tools.config_data_model import (
    SessionToolConfigBase,
    turn_pydantic_model_to_json_schema
)
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition

# 工具名称
TOOL_NAME = "bash"


class BashConfig(SessionToolConfigBase):
    """
    Bash 工具的配置类

    Attributes:
        enabled: 是否启用工具
        default_timeout: 默认命令超时时间（秒）
        max_timeout: 最大允许的超时时间（秒）
        pod_ready_timeout: Pod 就绪等待超时（秒）
    """
    enabled: bool = True
    explicit: bool = True
    default_timeout: float = Field(
        default=120.0,
        description="默认命令超时时间（秒），默认 120 秒"
    )
    max_timeout: float = Field(
        default=600.0,
        description="最大允许的命令超时时间（秒），默认 600 秒（10分钟）"
    )
    pod_ready_timeout: float = Field(
        default=300.0,
        description="Pod 就绪等待超时（秒），默认 300 秒（5分钟）"
    )


class BashToolParamDefine(BaseModel):
    """
    Bash 工具的参数定义

    重要提示：命令必须是单次执行的，不支持交互式会话。
    例如：不能使用 vim、top、python（无参数）等需要用户交互的命令。
    """
    command: str = Field(
        description=(
            "要执行的 bash 命令。"
            "注意：命令必须能够单次完成执行，不支持交互式输入。"
            "例如：可以使用 'ls -la'、'cat file.txt'、'pip install package'，"
            "但不能使用 'vim file.txt'、'top' 等需要交互的命令。"
        )
    )
    timeout: float | None = Field(
        default=None,
        description=(
            "命令超时时间（秒）。如果为 None，使用配置中的默认超时时间。"
            "最大值受配置中的 max_timeout 限制。"
        )
    )

    model_config = ConfigDict(extra='allow')


# 默认工具配置
DEFAULT_TOOL_CONFIG = {
    TOOL_NAME: BashConfig(enabled=True, explicit=True)
}


# 工具生成参数（用于 LLM Function Calling）
GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name=TOOL_NAME,
        description=(
            "在用户的容器环境中执行 bash 命令。"
            "该工具会自动拉起用户的容器（如果未运行），并在容器内执行指定的命令。\n\n"
            "重要限制：\n"
            "1. 命令必须能够单次执行完成，不支持交互式命令（如 vim、top、python 交互模式等）。\n"
            "2. 命令执行的超时时间有限制，长时间运行的命令可能会被中断。\n"
            "3. 容器内的工作目录默认为用户的 JuiceFS 挂载目录（/juice）。\n\n"
            "返回结果包含：\n"
            "- stdout: 命令的标准输出\n"
            "- stderr: 命令的标准错误输出\n"
            "- returncode: 命令的退出码（0 表示成功）\n"
            "- interrupted: 命令是否被中断\n"
            "- error: 执行过程中的错误信息（如果有）"
        ),
        parameters=turn_pydantic_model_to_json_schema(BashToolParamDefine),
        parameters_example={
            "command": "ls -la /juice && echo 'Hello World'",
            "timeout": 60
        }
    )  # type: ignore
)