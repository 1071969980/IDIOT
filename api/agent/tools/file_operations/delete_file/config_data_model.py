"""
delete_item 工具的配置和参数定义
"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

from api.agent.tools.config_data_model import SessionToolConfigBase
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition

TOOL_NAME = "delete_item"


class DeleteItemConfig(SessionToolConfigBase):
    """DeleteItem 工具的配置类"""
    enabled: bool = True
    storage_backend: Literal["memory", "local", "user_space", "kwargs_DI"] = Field(
        default="user_space",
        description="存储后端类型选择"
    )
    local_base_path: str | None = Field(
        default=None,
        description="本地文件系统的基础路径"
    )


class DeleteItemParamDefine(BaseModel):
    """DeleteItem 工具的参数定义"""
    path: str = Field(
        description="要删除的路径。文件或目录的相对路径。"
    )

    model_config = ConfigDict(extra='allow')


DEFAULT_TOOL_CONFIG = {
    TOOL_NAME: DeleteItemConfig(enabled=True, storage_backend="user_space")
}


DELETE_ITEM_GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name=TOOL_NAME,
        description=(
            "删除文件或目录。永久删除指定路径的文件或目录。"
            "警告: 此操作不可逆，请确保在删除前已确认路径正确。"
            "如果路径不存在会返回错误。执行结果会说明删除的是文件还是目录。"
        ),
        parameters=DeleteItemParamDefine.model_json_schema()
    )
)