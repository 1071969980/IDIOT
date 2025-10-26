from api.agent.tools.config_data_model import SessionToolConfigBase

TOOL_NAME = "create_chat_task_to_another_agent"

class CreateChatTaskToAnotherAgentConfig(SessionToolConfigBase):
    pass

DEFAULT_TOOL_CONFIG = {
    TOOL_NAME: CreateChatTaskToAnotherAgentConfig(enabled=True)
}