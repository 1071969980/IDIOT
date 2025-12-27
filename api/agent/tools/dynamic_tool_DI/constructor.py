from typing import Any, Callable, Coroutine, Type

from pydantic import BaseModel, ConfigDict, ValidationError, create_model
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from openai.types.shared_params import FunctionDefinition

from api.agent.tools.data_model import ToolTaskResult
from api.agent.tools.type import ToolClosure
from api.agent.tools.config_data_model import turn_pydantic_model_to_json_schema



def construct_tool(
    tool_name: str,
    tool_description: str,
    tool_param_model: type[BaseModel],
    call_back: Callable[[BaseModel], Coroutine[Any, Any, None]],
) -> tuple[ChatCompletionToolParam, ToolClosure]:

    chat_completion_tool_param = ChatCompletionToolParam(
        type="function",
        function=FunctionDefinition(
            name=tool_name,
            description=tool_description,
            parameters=turn_pydantic_model_to_json_schema(tool_param_model)
        )
    )

    async def tool(**kwargs: dict[str, Any]) -> ToolTaskResult:
        try:
            param = tool_param_model.model_validate(kwargs)
        except ValidationError as e:
            error_msg = "\n".join([error["msg"] for error in e.errors()])
            return ToolTaskResult(
                str_content=f"Invalid parameters: \n" + error_msg,
                occur_error=True,
            )
        
        await call_back(param)

        return ToolTaskResult(
            str_content="Success Execution."
        )


    return chat_completion_tool_param, tool

