"""
bash 工具的实现
"""

from typing import Any
from uuid import UUID

from pydantic import ValidationError
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
import logfire

from api.agent.tools.type import ToolClosure, ToolTaskResult
from api.user_pod_command.data_model import CommandResult
from .config_data_model import (
    BashConfig,
    BashToolParamDefine,
    GENERATION_TOOL_PARAM,
    TOOL_NAME
)
from api.user_pod_command import (
    pod_command_session,
    execute_command,
    UserPodCommandError,
    PodCreationTimeoutError,
    PodStatusAbnormalError,
)


class BashTool(object):
    """
    Bash 工具类

    在用户的容器中执行 bash 命令。
    """

    def __init__(
        self,
        config: BashConfig,
        user_id: UUID,
    ):
        """
        初始化工具

        Args:
            config: 工具配置
            user_id: 用户 ID，用于确定容器归属
        """
        self.config = config
        self.user_id = user_id

    async def __call__(self, **kwargs: dict[str, Any]) -> ToolTaskResult:
        """
        工具的调用入口

        Args:
            **kwargs: LLM 传递的参数
                - command: 要执行的命令（必需）
                - timeout: 超时时间（可选）

        Returns:
            ToolTaskResult: 执行结果
        """
        # 1. 参数验证
        try:
            param = BashToolParamDefine.model_validate(kwargs)
        except ValidationError as e:
            error_msg = "\n".join(
                f"{'.'.join(str(l) for l in err['loc'])} - {err['msg']}"
                for err in e.errors()
            )
            return ToolTaskResult(
                str_content=f"参数验证失败:\n{error_msg}",
                occur_error=True
            )

        # 2. 验证命令不为空
        if not param.command or not param.command.strip():
            return ToolTaskResult(
                str_content="错误：command 参数不能为空",
                occur_error=True
            )

        # 3. 确定超时时间
        timeout = param.timeout if param.timeout is not None else self.config.default_timeout
        # 限制最大超时时间
        if timeout > self.config.max_timeout:
            timeout = self.config.max_timeout

        # 4. 执行命令
        with logfire.span(
            "bash 工具执行命令",
            command=param.command,
            timeout=timeout,
            user_id=str(self.user_id)
        ):
            try:
                async with pod_command_session(
                    user_id=self.user_id,
                    image=self.config.image,
                    pod_ready_timeout=self.config.pod_ready_timeout,
                ) as session:
                    result = await execute_command(
                        pod_command_session_struct=session,
                        command=param.command,
                        timeout=timeout,
                    )
            except PodCreationTimeoutError as e:
                return ToolTaskResult(
                    str_content=f"容器创建超时：{str(e)}",
                    occur_error=True
                )
            except PodStatusAbnormalError as e:
                return ToolTaskResult(
                    str_content=f"容器状态异常：{str(e)}",
                    occur_error=True
                )
            except UserPodCommandError as e:
                return ToolTaskResult(
                    str_content=f"命令执行服务错误：{str(e)}",
                    occur_error=True
                )
            except Exception as e:
                logfire.error(f"bash 工具执行异常: {e}")
                return ToolTaskResult(
                    str_content=f"执行命令时发生未预期的错误：{str(e)}",
                    occur_error=True
                )

        # 5. 格式化并返回结果
        return self._format_result(param.command, result)

    def _format_result(
        self,
        command: str,
        result: CommandResult
    ) -> ToolTaskResult:
        """
        格式化命令执行结果

        Args:
            command: 执行的命令
            result: CommandResult 对象

        Returns:
            ToolTaskResult: 格式化后的结果
        """
        # 构建结果字符串
        output_parts = []

        # 基本信息
        output_parts.append(f"命令: {command}")
        output_parts.append(f"退出码: {result.returncode if result.returncode is not None else 'N/A'}")

        if result.interrupted:
            output_parts.append("状态: 命令被中断")
        elif result.error:
            output_parts.append(f"状态: 执行出错 - {result.error}")
        elif result.returncode == 0:
            output_parts.append("状态: 执行成功")
        else:
            output_parts.append(f"状态: 执行失败（退出码 {result.returncode}）")

        output_parts.append("")  # 空行分隔

        # stdout
        if result.stdout:
            output_parts.append("=== 标准输出 ===")
            output_parts.append(result.stdout)
            if not result.stdout.endswith('\n'):
                output_parts.append("")  # 确保末尾换行

        # stderr
        if result.stderr:
            output_parts.append("=== 标准错误 ===")
            output_parts.append(result.stderr)
            if not result.stderr.endswith('\n'):
                output_parts.append("")

        # 构建结构化结果
        json_content = {
            "command": command,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "interrupted": result.interrupted,
            "error": result.error,
        }

        return ToolTaskResult(
            str_content="\n".join(output_parts),
            json_content=json_content,
            occur_error=result.returncode != 0 if result.returncode is not None else False,
        )


def construct_tool(
    config: BashConfig,
    **kwargs: dict[str, Any]
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    """
    构造 BashTool 实例

    Args:
        config: 工具配置
        **kwargs: 依赖参数
            - user_id_for_scope (UUID, 必需): 用户 ID

    Returns:
        (GENERATION_TOOL_PARAM, tool_closure) 元组
    """
    # 提取 user_id（必需）
    user_id: UUID | None = kwargs.get("user_id_for_scope")  # type: ignore
    if user_id is None:
        raise ValueError("user_id_for_scope is required for bash tool")

    # 创建工具实例
    tool = BashTool(config=config, user_id=user_id)

    return (
        GENERATION_TOOL_PARAM,
        tool,
    )


# 构造器注册
CONSTRUCTOR = {TOOL_NAME: construct_tool}