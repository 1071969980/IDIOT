"""
bash 工具的实现
"""

import asyncio
from typing import Any, cast
from uuid import UUID

from pydantic import ValidationError
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
import logfire

from api.agent.tools.type import ToolClosure, ToolTaskResult
from api.agent.session_agent_config.utils import resolve_scope_value
from api.user_pod_command.data_model import CommandResult
from .config_data_model import (
    BashConfig,
    BashToolParamDefine,
    BashToolScope,
    BASH_USER_ID_PATHS,
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

    def __init__(self, config: BashConfig):
        self.config = config

    @property
    def user_id(self) -> UUID:
        return self.config.tool_scope.user_id_for_scope # type: ignore

    async def __call__(self, **kwargs: dict[str, Any]) -> ToolTaskResult:
        """
        工具的调用入口

        Args:
            **kwargs: LLM 传递的参数
                - command: 要执行的命令（必需）
                - timeout: 超时时间（可选）
                - cancel_event: 取消事件（由 base_agent 注入）

        Returns:
            ToolTaskResult: 执行结果
        """
        # 0. 提取 cancel_event（由 base_agent 注入），检查是否已被取消
        cancel_event = cast(
            asyncio.Event | None,
            kwargs.get("cancel_event"),
        )
        if cancel_event is not None and cancel_event.is_set():
            return ToolTaskResult(
                str_content="Bash 命令已被用户取消",
                occur_error=True,
            )

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
                        cancel_event=cancel_event,
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
        user_cancelled = (
            cancel_event is not None
            and cancel_event.is_set()
            and result.interrupted
        )
        return self._format_result(param.command, result, user_cancelled=user_cancelled)

    def _format_result(
        self,
        command: str,
        result: CommandResult,
        user_cancelled: bool = False,
    ) -> ToolTaskResult:
        """
        格式化命令执行结果

        Args:
            command: 执行的命令
            result: CommandResult 对象
            user_cancelled: 是否由用户主动取消触发

        Returns:
            ToolTaskResult: 格式化后的结果
        """
        # 构建结果字符串
        output_parts = []

        # 基本信息
        output_parts.append(f"命令: {command}")
        output_parts.append(f"退出码: {result.returncode if result.returncode is not None else 'N/A'}")

        if result.interrupted:
            if user_cancelled:
                output_parts.append("状态: Bash 命令已被用户中断")
            else:
                output_parts.append("状态: 命令被中断（Pod 状态异常或会话超时）")
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
    scope_def: dict[str, Any],
    **kwargs: dict[str, Any],
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    """
    构造 BashTool 实例

    Args:
        config: 工具配置
        scope_def: 作用域定义字典
        **kwargs: 依赖参数（ToolFactory 注入，bash 不使用）

    Returns:
        (GENERATION_TOOL_PARAM, tool_closure) 元组
    """
    # 优先级 1: config 已有 tool_scope
    scope = config.tool_scope

    # 优先级 2: 从 scope_def 解析
    if scope is None:
        user_id_raw = resolve_scope_value(scope_def, BASH_USER_ID_PATHS)
        user_id = UUID(user_id_raw) if isinstance(user_id_raw, str) else user_id_raw
        scope = BashToolScope(user_id_for_scope=user_id)

    # 写入 config
    config = config.model_copy(update={"tool_scope": scope})

    # 创建工具实例
    tool = BashTool(config=config)

    return (
        GENERATION_TOOL_PARAM,
        tool,
    )


# 构造器注册
CONSTRUCTOR = {TOOL_NAME: construct_tool}