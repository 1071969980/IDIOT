"""ask_user_offline_cli 工具的实现"""

from typing import Any
from uuid import UUID

from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from pydantic import BaseModel, ValidationError

from api.agent.tools.type import ToolClosure, ToolTaskResult
from .config_data_model import (
    TOOL_NAME,
    AskUserOfflineCliConfig,
    GENERATION_TOOL_PARAM,
    AskUserOfflineCliToolParamDefine,
)


class UserChoiceResponse(BaseModel):
    """用户选择响应模型"""

    is_additional: bool = False
    choice: str


class AskUserOfflineCliTool:
    """AskUserOfflineCli 工具类

    使用 input() 在命令行环境中向用户提问并获取选择
    """

    def __init__(self, config: AskUserOfflineCliConfig, session_id: UUID):
        """初始化工具

        Args:
            config: 工具配置
            session_id: 会话ID
        """
        self.config = config
        self.session_id = session_id

    async def __call__(self, **kwargs: dict[str, Any]) -> ToolTaskResult:
        """工具的调用入口

        Args:
            **kwargs: LLM 传递的参数

        Returns:
            ToolTaskResult: 执行结果
        """
        # 1. 参数验证
        try:
            param = AskUserOfflineCliToolParamDefine.model_validate(kwargs)
        except ValidationError as e:
            error_msg = "\n".join([error["msg"] for error in e.errors()])
            return ToolTaskResult(
                str_content=f"参数验证失败：\n{error_msg}", occur_error=True
            )

        # 2. 业务逻辑验证
        if not param.question:
            return ToolTaskResult(
                str_content="错误：question 不能为空", occur_error=True
            )

        if not param.options or len(param.options) == 0:
            return ToolTaskResult(
                str_content="错误：options 不能为空", occur_error=True
            )

        # 3. 获取用户输入（带重试机制）
        response = await self._get_user_input_with_retry(
            param.question, param.options, param.allow_additional_input
        )

        # 4. 格式化返回结果
        if response.is_additional:
            if response.choice.strip():
                str_content = "用户选择了自定义输入: " + response.choice
            else:
                str_content = "用户选择了自定义输入但未提供文本"
        else:
            choice_idx = int(response.choice)
            str_content = f"用户选择了选项 {choice_idx + 1}: {param.options[choice_idx]}"

        return ToolTaskResult(
            str_content=str_content,
            json_content={
                "question": param.question,
                "options": param.options,
                "allow_additional_input": param.allow_additional_input,
                "user_choice": response.choice,
                "is_additional": response.is_additional,
            },
            occur_error=False,
        )

    async def _get_user_input_with_retry(
        self, question: str, options: list[str], allow_additional_input: bool
    ) -> UserChoiceResponse:
        """获取用户输入，带重试机制

        Args:
            question: 问题文本
            options: 选项列表
            allow_additional_input: 是否允许额外输入

        Returns:
            UserChoiceResponse: 用户选择响应
        """
        while True:
            # 显示问题和选项
            print(f"\n{question}")
            print("=" * 60)
            for i, option in enumerate(options, 1):
                print(f"  {i}. {option}")

            if allow_additional_input:
                print("  (或直接输入自定义内容)")

            print("=" * 60)

            # 获取用户输入
            user_input = input("请输入选项序号: ").strip()

            # 尝试解析为数字
            try:
                choice_num = int(user_input)

                # 处理选项序号 (1-based -> 0-based)
                if 1 <= choice_num <= len(options):
                    return UserChoiceResponse(
                        is_additional=False, choice=str(choice_num - 1)
                    )
                else:
                    print(f"错误：序号必须在 1-{len(options)} 之间")
                    print("请重新输入\n")

            except ValueError:
                # 输入不是数字
                if allow_additional_input:
                    # 如果允许额外输入，将其视为自定义输入
                    return UserChoiceResponse(is_additional=True, choice=user_input)
                else:
                    # 不允许额外输入，提示重试
                    print(f"错误：请输入有效的序号（1-{len(options)}）")
                    print("请重新输入\n")


def construct_ask_user_offline_cli(
    config: AskUserOfflineCliConfig, **kwargs: dict[str, Any]
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    """构造 AskUserOfflineCliTool 实例

    Args:
        config: 工具配置
        **kwargs: 依赖参数
            - session_id (UUID, 必需): 会话ID

    Returns:
        (GENERATION_TOOL_PARAM, tool_closure) 元组
    """
    # 提取 session_id（必需）
    session_id: UUID | None = kwargs.get("session_id")  # type: ignore
    if session_id is None:
        raise ValueError("session_id is required")

    # 创建工具实例
    tool = AskUserOfflineCliTool(config=config, session_id=session_id)

    # 返回工具定义和闭包
    return (GENERATION_TOOL_PARAM, tool)


# 构造器注册
CONSTRUCTOR = {TOOL_NAME: construct_ask_user_offline_cli}
