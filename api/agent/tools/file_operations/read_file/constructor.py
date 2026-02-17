"""
read_file 工具的实现
"""

from typing import Any

from pydantic import ValidationError
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

# 导入项目的基础类型
from api.agent.tools.type import ToolClosure, ToolTaskResult
from .config_data_model import (
    ReadFileConfig,
    ReadFileParamDefine,
    READ_FILE_GENERATION_TOOL_PARAM,
    TOOL_NAME
)
# 导入存储后端
from ..storage_backend.base import FileOperationsStorageBackend
from ..storage_backend.memory import MemoryFileBackend
from ..storage_backend.local import LocalFileBackend
from ..storage_backend.user_space import UserSpaceFileBackend


class ReadFileTool(object):
    """
    ReadFile 工具类

    提供读取文件内容的功能，支持偏移量、行数限制和行号显示。
    """

    def __init__(self, config: ReadFileConfig, storage_backend: FileOperationsStorageBackend):
        """
        初始化工具

        Args:
            config: 工具配置
            storage_backend: 存储后端实例（已持有 session_id）
        """
        self.config = config
        self.storage_backend = storage_backend

    async def __call__(self, **kwargs: dict[str, Any]) -> ToolTaskResult:
        """
        工具的调用入口

        Args:
            **kwargs: LLM 传递的参数

        Returns:
            ToolTaskResult: 执行结果
        """
        # 1. 参数验证
        try:
            param = ReadFileParamDefine.model_validate(kwargs)
        except ValidationError as e:
            error_msg = "\n".join([error["msg"] for error in e.errors()])
            return ToolTaskResult(
                str_content=f"参数验证失败：\n{error_msg}",
                occur_error=True
            )

        # 2. 业务逻辑验证
        if not param.file_path:
            return ToolTaskResult(
                str_content="错误：file_path 不能为空",
                occur_error=True
            )

        if param.offset is not None and param.offset < 0:
            return ToolTaskResult(
                str_content="错误：offset 必须大于等于 0",
                occur_error=True
            )

        if param.limit is not None and param.limit <= 0:
            return ToolTaskResult(
                str_content="错误：limit 必须大于 0",
                occur_error=True
            )

        # 3. 调用存储后端读取文件
        try:
            content, first_line, total_lines = await self.storage_backend.read_file(
                param.file_path,
                param.offset,
                param.limit
            )
        except FileNotFoundError:
            return ToolTaskResult(
                str_content=f"文件不存在：{param.file_path}",
                occur_error=True
            )
        except PermissionError:
            return ToolTaskResult(
                str_content=f"无权限访问文件：{param.file_path}",
                occur_error=True
            )
        except ValueError as e:
            return ToolTaskResult(
                str_content=f"路径错误：{str(e)}",
                occur_error=True
            )
        except Exception as e:
            return ToolTaskResult(
                str_content=f"读取文件时发生错误：{str(e)}",
                occur_error=True
            )

        # 4. 格式化输出（自动添加行号和截断长行）
        formatted_content = self._format_output(
            content,
            param.file_path,
            first_line,
            total_lines
        )

        return ToolTaskResult(
            str_content=formatted_content,
            occur_error=False
        )

    def _format_output(
        self,
        content: str,
        file_path: str,
        first_line_number: int,
        total_lines: int
    ) -> str:
        """
        格式化输出内容

        参考 api/agent/tools/read_file/utils.py 的格式化风格：
        - 自动显示行号（使用 → 符号，右对齐5个字符）
        - 长行截断（单行超过1000字符时截断并添加标记）

        Args:
            content: 文件内容
            file_path: 文件路径
            first_line_number: 第一行的行号
            total_lines: 文件总行数

        Returns:
            格式化后的输出字符串
        """
        lines = content.split('\n')

        # 处理空文件
        if not lines or (len(lines) == 1 and not lines[0]):
            return f"文件内容：{file_path}\n文件为空"

        # 格式化每一行：添加行号、截断长行
        formatted_lines = []
        for i, line in enumerate(lines):
            # 截断长行（参考 utils.py 的实现）
            if len(line) > 1000:
                line = line[:1000] + "... [line be truncated]"

            # 添加行号（右对齐5个字符）
            line_number = i + first_line_number
            formatted_line = (f"{line_number}→").rjust(5, " ") + line
            formatted_lines.append(formatted_line)

        formatted_content = '\n'.join(formatted_lines)

        # 计算实际读取的行数
        lines_count = len(lines)
        last_line_number = first_line_number + lines_count - 1 if lines_count > 0 else first_line_number

        header = (
            f"文件内容：{file_path}\n"
            f"读取行数：{first_line_number}-{last_line_number} / 共{total_lines}行\n"
        )

        return header + "\n" + formatted_content


def construct_read_file(
    config: ReadFileConfig,
    **kwargs: dict[str, Any]
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    """
    构造 ReadFileTool 实例

    Args:
        config: 工具配置
        **kwargs: 依赖参数
            - session_id (UUID, 必需): 用于注入到存储后端
            - user_id (UUID, 可选): UserSpaceFileBackend 需要
            - storage_backend (FileOperationsStorageBackend, 可选): 当 config.storage_backend="kwargs_DI" 时必需

    Returns:
        (GENERATION_TOOL_PARAM, tool_closure) 元组
    """

    # 1. 提取 session_id（必需）
    from uuid import UUID
    session_id: UUID | None = kwargs.get("session_id")  # type: ignore
    if session_id is None:
        raise ValueError("session_id is required")

    # 2. 提取 user_id（某些后端需要）
    user_id: UUID | None = kwargs.get("user_id_for_scope")  # type: ignore

    # 3. 根据 config.storage_backend 创建存储后端
    if config.storage_backend == "memory":
        # 模式 1: Memory Storage
        storage_backend = MemoryFileBackend(session_id=session_id)

    elif config.storage_backend == "local":
        # 模式 2: Local Storage
        base_path = config.local_base_path or "/tmp/file_tools"
        storage_backend = LocalFileBackend(
            session_id=session_id,
            base_path=base_path
        )

    elif config.storage_backend == "user_space":
        # 模式 3: User Space Storage
        if user_id is None:
            raise ValueError(
                "user_id is required when config.storage_backend='user_space'"
            )
        storage_backend = UserSpaceFileBackend(
            session_id=session_id,
            user_id=user_id
        )

    elif config.storage_backend == "kwargs_DI":
        # 模式 4: 依赖注入
        storage_backend: FileOperationsStorageBackend | None = kwargs.get("storage_backend")  # type: ignore

        if storage_backend is None:
            raise ValueError(
                "storage_backend must be provided in kwargs "
                "when config.storage_backend='kwargs_DI'"
            )

        # 类型验证
        if not isinstance(storage_backend, FileOperationsStorageBackend):
            raise TypeError(
                f"storage_backend must be an instance of FileOperationsStorageBackend, "
                f"got {type(storage_backend).__name__}"
            )

    else:
        # 不应该到达这里（Pydantic 会验证 config.storage_backend）
        raise ValueError(f"Unknown storage_backend type: {config.storage_backend}")

    # 4. 创建工具实例
    tool = ReadFileTool(config=config, storage_backend=storage_backend)

    # 5. 返回工具定义和闭包
    return (
        READ_FILE_GENERATION_TOOL_PARAM,
        tool
    )


# 构造器注册
CONSTRUCTOR = {TOOL_NAME: construct_read_file}
