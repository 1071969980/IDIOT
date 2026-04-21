# api/agent/tools/feed_message/constructor.py

"""feed_message 工具的构造器和实现。"""

import asyncio
import logfire
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

from api.agent.tools.data_model import ToolTaskResult
from api.agent.tools.type import ToolClosure
from api.chat.sql_stat.u2a_session_branch_task.operations import get_or_create_pending_task
from api.chat.sql_stat.u2a_user_msg.utils import (
    insert_user_message,
    _U2AUserMessageCreate,
)

from api.agent.xml_marks_def import EXTERNAL_MESSAGE_BLOCK_START, EXTERNAL_MESSAGE_BLOCK_END
from api.chat.schedule_pending_task import schedule_pending_task
from api.chat.sql_stat.u2a_session_branch_task.storage_snapshot_op import get_branch_storage_snapshot

from .config_data_model import (
    FeedMessageConfig,
    FeedMessageParamDefine,
    GENERATION_TOOL_PARAM,
    TOOL_NAME,
)


class FeedMessageTool:
    """向 pending session_task 发送消息的工具。"""

    def __init__(self, 
                config: FeedMessageConfig,
                user_id: UUID,
                session_id: UUID,
                calling_branch_name: str,
                llm_service_name: str):
        self.config = config
        self.user_id = user_id
        self.session_id = session_id
        self.calling_branch_name = calling_branch_name
        self.llm_service_name = llm_service_name

    async def __call__(self, **kwargs: dict[str, Any]) -> ToolTaskResult:
        # 参数验证
        try:
            param = FeedMessageParamDefine.model_validate(kwargs)
        except ValidationError as e:
            error_msg = "\n".join([error["msg"] for error in e.errors()])
            return ToolTaskResult(
                str_content=f"参数验证失败:\n{error_msg}",
                occur_error=True,
            )

        # 统一为列表
        messages: list[str] = [param.message] if isinstance(param.message, str) else param.message

        # 解析别名到分支名
        target_branch_name: str
        if param.sub_agent_alias is not None:
            try:
                _, snapshot = await get_branch_storage_snapshot(
                    session_id=self.session_id,
                    user_id=self.user_id,
                    branch_name=self.calling_branch_name,
                )
            except ValueError as e:
                return ToolTaskResult(
                    str_content=f"无法读取当前分支的 storage_snapshot: {e}",
                    occur_error=True,
                )
            aliases: dict[str, str] = snapshot.get("sub_agent_aliases", {})
            resolved = aliases.get(param.sub_agent_alias)
            if resolved is None:
                available = ", ".join(f"`{k}` -> `{v}`" for k, v in aliases.items()) if aliases else "（无已注册的子代理别名）"
                return ToolTaskResult(
                    str_content=f"未找到别名 `{param.sub_agent_alias}` 对应的子代理分支。"
                                f"当前已注册的别名: {available}",
                    occur_error=True,
                )
            target_branch_name = resolved
        else:
            target_branch_name = param.branch_name  # type: ignore[arg-type]

        # 获取或创建 pending task
        try:
            session_task_id, is_new_task = await get_or_create_pending_task(
                session_id=self.session_id,
                user_id=self.user_id,
                branch_name=target_branch_name,
            )
        except ValueError as e:
            return ToolTaskResult(
                str_content=f"获取 pending 任务失败: {e}",
                occur_error=True,
            )

        # 逐条插入消息
        inserted_ids: list[str] = []
        for msg_content in messages:
            message_data = _U2AUserMessageCreate(
                user_id=self.user_id,
                session_id=self.session_id,
                message_type="text",
                content=self.format_msg(msg_content),
                status="waiting_agent_ack_user",
                session_task_id=session_task_id,
                process_priority=20,
            )
            message_id = await insert_user_message(message_data)
            inserted_ids.append(str(message_id))

        # 计划处理任务
        asyncio.create_task(  # noqa: RUF006
            schedule_pending_task(self.user_id,
                                  self.session_id,
                                  target_branch_name,
                                  self.llm_service_name)
        )

        if param.sub_agent_alias is not None:
            success_msg = (
                f"已通过别名 '{param.sub_agent_alias}' 向分支 '{target_branch_name.split(":")[0]}' 发送 {len(inserted_ids)} 条消息"
            )
        else:
            success_msg = (
                f"已向分支 '{target_branch_name}' 发送 {len(inserted_ids)} 条消息"
            )

        return ToolTaskResult(
            str_content=success_msg,
            json_content={
                "session_task_id": str(session_task_id),
                "is_new_task": is_new_task,
                "message_ids": inserted_ids,
            },
            occur_error=False,
        )

    def format_msg(self, message)-> str:
        return (
            f"{EXTERNAL_MESSAGE_BLOCK_START}\n"
            "---\n"
            "created_by: feed_message tool\n"
            f"from: {self.calling_branch_name.split(":")[0]}\n"
            "---\n\n"
            f"{message}\n"
            f"{EXTERNAL_MESSAGE_BLOCK_END}\n"
        )

def construct_feed_message(
    config: FeedMessageConfig,
    **kwargs: dict[str, Any],
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    """构造 feed_message 工具实例。

    Args:
        config: 工具配置
        **kwargs: 注入参数（需要 user_id, session_id）

    Returns:
        (工具参数, 工具闭包) 元组

    Raises:
        ValueError: 缺少必需参数时
    """
    user_id: UUID | None = kwargs.get("user_id")
    session_id: UUID | None = kwargs.get("session_id")
    branch_name: str | None = kwargs.get("branch_name")
    llm_service_name: str | None = kwargs.get("llm_service_name")

    if user_id is None:
        raise ValueError("user_id is required")
    if session_id is None:
        raise ValueError("session_id is required")
    if branch_name is None:
        raise ValueError("branch_name is required")
    if llm_service_name is None:
        raise ValueError("llm_service_name is required")

    tool = FeedMessageTool(config=config,
                           user_id=user_id,
                           session_id=session_id,
                           calling_branch_name=branch_name,
                           llm_service_name=llm_service_name)

    return (GENERATION_TOOL_PARAM, tool)


CONSTRUCTOR = {TOOL_NAME: construct_feed_message}
