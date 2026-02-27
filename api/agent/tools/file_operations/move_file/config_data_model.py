"""
move_item 工具的配置和参数定义
"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

from api.agent.tools.config_data_model import SessionToolConfigBase
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition

TOOL_NAME = "move_item"


class MoveItemConfig(SessionToolConfigBase):
    """MoveItem 工具的配置类"""
    enabled: bool = True
    storage_backend: Literal["memory", "local", "user_space", "kwargs_DI"] = Field(
        default="user_space",
        description="存储后端类型选择"
    )
    local_base_path: str | None = Field(
        default=None,
        description="本地文件系统的基础路径"
    )


class MoveItemParamDefine(BaseModel):
    """MoveItem 工具的参数定义"""
    source_path: str = Field(
        description="源路径。要移动的文件或目录的相对路径。"
    )
    destination_path: str = Field(
        description="目标路径。移动后的新路径。"
    )

    model_config = ConfigDict(extra='allow')


DEFAULT_TOOL_CONFIG = {
    TOOL_NAME: MoveItemConfig(enabled=True, storage_backend="user_space")
}


MOVE_ITEM_GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name=TOOL_NAME,
        description=(
            "移动或重命名文件或目录。将文件或目录从一个位置移动到另一个位置。"
            "如果源路径不存在会返回错误。如果目标路径已存在会返回错误。"
            "可用于重命名文件或目录（将移动到同一目录下的不同名称）。"
            "执行结果会说明操作的是文件还是目录。"
        ),
        parameters=MoveItemParamDefine.model_json_schema()
    )
)