from typing import Any
from uuid import UUID
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from pydantic import BaseModel, ValidationError

from api.agent.tools.type import ToolClosure, ToolTaskResult
from .config_data_model import (
    TOOL_NAME,
    AskUserChoiceConfig,
    GENERATION_TOOL_PARAM,
    AskUserChoiceToolParamDefine,
)
from api.human_in_loop.interrupt import (
    interrupt as HIL_interrupt,
    HILInterruptContent,
    HILInterruptContentAgentToolCallBody,
    HILInterruptContentAgentToolCallBodyType,
)

class UserChoiceResponse(BaseModel):
    is_additional: bool = False
    choice: str

class AskUserChoiceTool(object):
    def __init__(self, 
                 config: AskUserChoiceConfig,
                 session_task_id: UUID):
        self.config = config
        self.session_task_id = session_task_id

    async def __call__(self, **kwargs: dict[str, Any]) -> ToolTaskResult:
        """
        Ask user choice
        """
        try:
            param = AskUserChoiceToolParamDefine.model_validate(kwargs)
        except ValidationError as e:
            error_msg = "\n".join([error["msg"] for error in e.errors()])
            return ToolTaskResult(
                str_content=f"Invalid parameters: \n" + error_msg,
                occur_error=True,
            )

        if param.model_extra is None:
            raise ValueError("exec_uuid is required")
        exec_uuid = param.model_extra.get("exec_uuid")
        if exec_uuid is None:
            raise ValueError("exec_uuid is required")
        
        # collect all model_extra keys 
        extra_keys = set(param.model_extra.keys())
        
        hil_content = HILInterruptContent(
            source="agent_tool_call",
            body=HILInterruptContentAgentToolCallBody(
                tool_name=TOOL_NAME,
                type=HILInterruptContentAgentToolCallBodyType.ChoiceForm,
                tool_exec_uuid=str(exec_uuid),
                detail=param.model_dump(mode="json", exclude=extra_keys),
            ),
        )

        response = await HIL_interrupt(
            content=hil_content,
            stream_identifier=str(self.session_task_id)
        )

        response = UserChoiceResponse.model_validate(response)

        if response.is_additional:
            if response.choice.strip():
                str_content = "User choosed additional input: " + response.choice
            else:
                str_content = "User choosed additional input but no text provided"
        else:
            str_content = "User choosed option: " + response.choice
        
        return ToolTaskResult(
            str_content=str_content,
            json_content={
                **param.model_dump(mode="json", exclude=extra_keys),
                "user_choice": response.choice,
            },
            occur_error=False,
            HIL_data=[hil_content]
        )


def construct_tool(
    config: AskUserChoiceConfig, 
    **kwargs: dict[str, Any]
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    session_task_id : UUID | None = kwargs.get("session_task_id") # type: ignore
    if session_task_id is None:
        raise ValueError("session_task_id is required")

    tool = AskUserChoiceTool(config, session_task_id)

    return (
        GENERATION_TOOL_PARAM,
        tool,
    )


CONSTRUCTOR = {TOOL_NAME: construct_tool}
