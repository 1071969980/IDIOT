"""
copy_item 工具的配置和参数定义
"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

from api.agent.tools.config_data_model import SessionToolConfigBase
from ..config_scope_data_model import FileOpsToolScope
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition

TOOL_NAME = "copy_item"


class CopyItemConfig(SessionToolConfigBase):
    """CopyItem 工具的配置类"""
    enabled: bool = True
    explicit: bool = True
    storage_backend: Literal["kwargs_DI", "juicefs_sdk"] = Field(
        default="juicefs_sdk",
        description="存储后端类型选择。'juicefs_sdk' 使用 JuiceFS SDK 直接操作文件系统（推荐）；'kwargs_DI' 从依赖注入获取存储后端实例。"
    )
    tool_scope: FileOpsToolScope | None = None


class CopyItemParamDefine(BaseModel):
    """CopyItem 工具的参数定义"""
    source_path: str = Field(
        description="源路径。要复制的文件或目录的相对路径。"
    )
    destination_path: str = Field(
        description="目标路径。复制后的新路径。"
    )

    model_config = ConfigDict(extra='allow')


DEFAULT_TOOL_CONFIG = {
    TOOL_NAME: CopyItemConfig(enabled=True, explicit=False, storage_backend="juicefs_sdk")
}


COPY_ITEM_GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name=TOOL_NAME,
        description=(
            "复制文件或目录。创建源文件或目录的副本到目标位置。"
            "如果源路径不存在会返回错误。如果目标路径已存在会返回错误。"
            "原始文件或目录保持不变。执行结果会说明操作的是文件还是目录。"
        ),
        parameters=CopyItemParamDefine.model_json_schema()
    )
)