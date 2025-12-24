from __future__ import annotations

from typing import Any
from uuid import UUID

from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from pydantic import ValidationError
import ujson

from api.agent.tools.data_model import ToolTaskResult
from api.agent.tools.type import ToolClosure

from .config_data_model import (
    GENERATION_TOOL_PARAM,
    TOOL_NAME,
    UpdateConversationStrategiesOfRoleToolParamDefine,
    UpdateConversationStrategiesOfRoleToolConfig,
)

from ..utils import user_agent_role_strategies_update_cache_file

class UpdateConversationStrategiesOfRoleTool:
    """
    请求更新角色的对话策略的工具类的实现
    """

    def __init__(self,
                config: UpdateConversationStrategiesOfRoleToolConfig,
                user_id: UUID):
        self.config = config
        self.user_id = user_id

    async def __call__(self, **kwargs: dict[str, Any]) -> ToolTaskResult:
        try:
            param = UpdateConversationStrategiesOfRoleToolParamDefine.model_validate(kwargs)
        except ValidationError as e:
            error_msg = "\n".join([error["msg"] for error in e.errors()])
            return ToolTaskResult(
                str_content=f"Invalid parameters: \n" + error_msg,
                occur_error=True,
            )
        
        update_cache_file = user_agent_role_strategies_update_cache_file(self.user_id, param.role_name, "w")
        
        async with update_cache_file:
            update_cache_json = {}
            update_cache_json_byte = update_cache_file.read()
            try:
                update_cache_json_str = update_cache_json_byte.decode("utf-8")
                update_cache_json = ujson.loads(update_cache_json_str)
            except Exception:
                pass
            if "strategies_update_cache" in update_cache_json and \
             isinstance(update_cache_json["strategies_update_cache"], list):
                update_cache_json["strategies_update_cache"].append(
                    {
                        "update_content": param.update_content,
                        "context": param.context,
                    }
                )
            else:
                update_cache_json["strategies_update_cache"] = {
                    "update_content": param.update_content,
                    "context": param.context,
                }
            
            update_cache_file.write(ujson.dumps(update_cache_json).encode("utf-8"))

        return ToolTaskResult(
            str_content=f"Request to update conversation strategies of role {param.role_name} successfully",
        )
            


def construct_tool(
    config: UpdateConversationStrategiesOfRoleToolConfig,
    **kwargs: dict[str, Any],
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    """
    构造 Characters 工具

    Args:
        config: 工具配置
        **kwargs: 其他参数，必须包含 user_id

    Returns:
        tuple: (工具参数定义, 工具实例)
    """
    user_id: UUID | None = kwargs.get("user_id") # type: ignore
    if user_id is None:
        raise ValueError("user_id is required")

    tool = UpdateConversationStrategiesOfRoleTool(config, user_id)

    return (
        GENERATION_TOOL_PARAM,
        tool,
    )


# 构造器注册
CONSTRUCTOR = {TOOL_NAME: construct_tool}
