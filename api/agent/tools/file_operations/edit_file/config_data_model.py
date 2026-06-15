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
from ..config_scope_data_model import FileOpsToolScope
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition

from .types import EditOp

# 工具名称
TOOL_NAME = "edit_file"


class EditFileConfig(SessionToolConfigBase):
    """EditFile 工具的配置类"""

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
    tool_scope: FileOpsToolScope | None = None


class EditFileParamDefine(BaseModel):
    """EditFile 工具的参数定义。

    支持 4 种编辑操作 (op):
    - replace: 替换一行 (仅 pos) 或一个范围 (pos + end)。需提供 pos 和 lines。
    - append: 在指定行之后插入。省略 pos 则追加到文件末尾。需提供 lines。
    - prepend: 在指定行之前插入。省略 pos 则插入到文件开头。需提供 lines。
    - replace_text: 替换文件中的精确唯一子串。需提供 oldText 和 newText。

    pos 和 end 为锚点引用格式 "<行号>#<3字符哈希>"，如 "5#MQP"。
    lines 为纯文件内容，不得包含 LINE#HASH: 前缀。
    """

    file_path: str = Field(
        description="要编辑的文件路径。相对于用户工作目录的路径。"
    )
    op: EditOp = Field(
        description=(
            "编辑操作类型。"
            "'replace': 替换行（pos 指定起始行，end 指定结束行，省略 end 则替换单行）。"
            "'append': 在 pos 行之后插入新行，省略 pos 则追加到文件末尾。"
            "'prepend': 在 pos 行之前插入新行，省略 pos 则插入到文件开头。"
            "'replace_text': 替换精确子串（类似传统 find-and-replace）。"
        )
    )

    # replace / append / prepend: 锚点引用
    pos: str | None = Field(
        default=None,
        description=(
            "锚点引用，格式为 '<行号>#<3字符哈希>'，如 '5#MQP'。"
            "用于 replace（必需）、append/prepend（可选，省略则操作文件首尾）。"
        )
    )
    end: str | None = Field(
        default=None,
        description=(
            "结束行锚点引用（仅 replace 使用）。"
            "省略则仅替换 pos 所在行。包含 end 行。"
        )
    )
    lines: str | None = Field(
        default=None,
        description=(
            "新内容（replace/append/prepend 使用），换行符分隔多行。"
            "不得以 LINE#HASH: 前缀开头。"
        )
    )

    # replace_text
    oldText: str | None = Field(
        default=None,
        description="要替换的文本（仅 replace_text 使用）。必须精确匹配。"
    )
    newText: str | None = Field(
        default=None,
        description="替换后的文本（仅 replace_text 使用）。"
    )
    replace_all: bool = Field(
        default=False,
        description="是否替换所有匹配项（仅 replace_text 使用）。"
    )

    model_config = ConfigDict(extra='allow')


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
        description=(
            "编辑文件内容。支持 4 种操作："
            "replace（替换行，通过锚点引用定位）、"
            "append（在指定行后插入）、"
            "prepend（在指定行前插入）、"
            "replace_text（替换精确子串）。"
            "编辑成功后返回 Edit Anchors，可用于后续链式编辑。"
        ),
        parameters=turn_pydantic_model_to_json_schema(EditFileParamDefine),
        parameters_example={
            "file_path": "src/main.py",
            "op": "replace",
            "pos": "5#MQP",
            "lines": "def hello():\n    pass"
        }
    )  # type: ignore
)
