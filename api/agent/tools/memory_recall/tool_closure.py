"""return_memory_recall 工具闭包构造"""

from typing import TYPE_CHECKING

from pydantic import ValidationError
from openai.types.chat.chat_completion_system_message_param import (
    ChatCompletionSystemMessageParam,
)

from api.agent.memory_trails.trails import MemoryTrails
from api.agent.tools.data_model import ToolTaskResult
from api.agent.tools.type import ToolClosure
from api.agent.xml_marks_def import MEMORY_RECALL_BLOCK_START, MEMORY_RECALL_BLOCK_END

from .config_data_model import ReturnMemoryRecallParamDefine

if TYPE_CHECKING:
    from api.agent.tools.file_operations.storage_backend.juicefs_sdk import JuiceFSSdkBackend


def make_return_memory_recall_closure(
    memory_trails: MemoryTrails,
    juicefs_backend: "JuiceFSSdkBackend",
) -> ToolClosure:
    """构造 return_memory_recall 工具闭包。

    Args:
        memory_trails: 运行时记忆路径集
        juicefs_backend: JuiceFS 文件操作后端，用于读取记忆文件内容
    """

    async def closure(**kwargs) -> ToolTaskResult:
        try:
            param = ReturnMemoryRecallParamDefine.model_validate(kwargs)
        except ValidationError as e:
            error_msg = "\n".join([error["msg"] for error in e.errors()])
            return ToolTaskResult(
                str_content=f"参数验证失败：\n{error_msg}",
                occur_error=True,
            )

        target = param.target_marker

        # 读取 mem_files 内容，每个文件独立用 <memory_recall> 标记包裹
        blocks: list[str] = []
        for file_path in param.mem_files:
            try:
                content, _, _ = await juicefs_backend.read_file(file_path)
            except Exception as e:
                return ToolTaskResult(
                    str_content=f"读取文件失败 {file_path}: {e}",
                    occur_error=True,
                )
            blocks.append(
                f"{MEMORY_RECALL_BLOCK_START}\n{content}\n{MEMORY_RECALL_BLOCK_END}"
            )

        msg = ChatCompletionSystemMessageParam(
            role="system",
            content="\n".join(blocks),
        )
        memory_trails.append_to_marker(target, msg, is_new=True)
        return ToolTaskResult(
            str_content=f"已将 {len(param.mem_files)} 个记忆文件注入到 {target} Marker"
        )

    return closure
