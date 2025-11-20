from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

from api.agent.tools.type import ToolClosure

from .config_data_model import TOOL_NAME, CreateCommunicationTaskConfig, CreateCommunicationTaskToolParamDefine, GENERATION_TOOL_PARAM
from typing import Any
from .sql_stat.a2a_session.utils import (
    _A2ASessionCreate,
    insert_session as insert_a2a_session,
    get_session as get_a2a_session,
)
from .sql_stat.a2a_session_task.utils import (
    _A2ASessionTaskCreate,
    insert_task as insert_a2a_session_task,
)

from api.agent.tools.data_model import ToolTaskResult, A2ASessionLinkData
from pydantic import ValidationError
from uuid import UUID
from api.authentication.sql_stat.utils import (
    get_user,
    get_user_by_username
)
import contextlib

class CreateCommunicationTaskTool:
    def __init__(self, 
                 config: CreateCommunicationTaskConfig,
                 source_user_id: UUID):
        self.config = config
        self.source_user_id: UUID  = source_user_id

    async def __call__(self, **kwargs: dict[str, Any]) -> ToolTaskResult:
        # 获取参数
        if self.source_user_id is None:
            raise ValueError("source_user is required")
        try:
            param = CreateCommunicationTaskToolParamDefine.model_validate(kwargs)
        except ValidationError as e:
            error_msg = "\n".join([error["msg"] for error in e.errors()])
            return ToolTaskResult(
                str_content=f"Invalid parameters: \n" + error_msg,
                occur_error=True,
            )
        
        # 验证目标用的合法性
        target_user = None
        with contextlib.suppress(Exception):
            tartget_user_id = UUID(param.target_user)
            target_user = await get_user(tartget_user_id)
            
        with contextlib.suppress(Exception):
            target_user = await get_user_by_username(param.target_user)
        
        if target_user is None:
            return ToolTaskResult(
                str_content=f"Invalid target_user: {param.target_user}",
                occur_error=True,
            )
        
        # 创建会话任务
        if param.session_id is None:
            session_id = await insert_a2a_session(
                _A2ASessionCreate(
                    user_a_id=self.source_user_id,
                    user_b_id=target_user.id,
                )
            )

            await insert_a2a_session_task(
                _A2ASessionTaskCreate(
                    session_id=session_id,
                    status="pending",
                    priority=100,
                    proactive_side="A",
                    params={
                        "goal": param.goal,
                    },
                )
            )

            return ToolTaskResult(
                str_content=f"Session {str(session_id)} created. \n",
                a2a_session_link_data=A2ASessionLinkData(
                    goal=param.goal,
                    session_id=str(session_id),
                )
            )

        
        # 在已有会话上创建任务
        else:
            session = await get_a2a_session(param.session_id)
            if session is None:
                return ToolTaskResult(
                    str_content=f"Invalid session_id: {param.session_id}",
                    occur_error=True,
                )
            
            proactive_side = None
            if session.user_a_id == self.source_user_id:
                proactive_side = "A"
            if session.user_b_id == self.source_user_id:
                proactive_side = "B"
            if proactive_side is None:
                return ToolTaskResult(
                    str_content=f"Invalid session_id: {param.session_id}",
                    occur_error=True,
                )

            await insert_a2a_session_task(
                _A2ASessionTaskCreate(
                    session_id=param.session_id,
                    status="pending",
                    priority=100,
                    proactive_side=proactive_side,
                    params={
                        "goal": param.goal,
                    },
                )
            )

            return ToolTaskResult(
                str_content=f"Session {str(param.session_id)} created. \n",
                a2a_session_link_data=A2ASessionLinkData(
                    goal=param.goal,
                    session_id=str(param.session_id),
                )
            )



def construct_tool(
    config: CreateCommunicationTaskConfig,
    **kwargs: dict[str, Any]
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    source_user_id :UUID | None = kwargs.get("user_id") # type: ignore
    if source_user_id is None:
        raise ValueError("user_id is required")

    tool = CreateCommunicationTaskTool(config, source_user_id=source_user_id)
    tool.set_source_user_id(source_user_id)

    return (
        GENERATION_TOOL_PARAM,
        tool,
    )


CONSTRUCTOR = {TOOL_NAME: construct_tool}
