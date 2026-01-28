# api/agent/tools/sub_agent/config_data_model.py

"""sub_agent 工具的配置和参数定义。"""

from pydantic import BaseModel, Field

from api.agent.tools.config_data_model import SessionToolConfigBase


class SubAgentToolConfig(SessionToolConfigBase):
    pass

class SubAgentParamDefine(BaseModel):
    """sub_agent 工具的参数定义。"""

    agent_name: str = Field(
        ...,
        description="要执行的子 agent 名称"
    )
    task: str = Field(
        ...,
        description="给子 agent 的任务安排文本"
    )
    session_alias: str | None = Field(
        None,
        description="要复用的子 agent 会话别名（仅在同一主 agent 会话中有效）"
    )


# 工具名称常量
TOOL_NAME = "sub_agent"

# 默认配置
DEFAULT_TOOL_CONFIG = SubAgentToolConfig(enabled=True)
