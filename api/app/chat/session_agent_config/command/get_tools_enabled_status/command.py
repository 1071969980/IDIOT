from typing import TYPE_CHECKING, List, Optional
from .data_model import (
    GetToolsEnabledStatusInput,
    GetToolsEnabledStatusOutput,
    ToolEnabledStatus,
    ToolNameEnum
)
from ..base import AbstractCommand
from api.agent.sql_stat.u2a_session_agent_config.utils import (
    get_session_config_by_session_id,
    _U2ASessionAgentConfig
)
from api.agent.session_agent_config.config_data_model import SessionAgentConfig, DEFAULT_TOOLS_CONFIG
from uuid import UUID

if TYPE_CHECKING:
    from typing import Optional


class GetToolsEnabledStatusCommand(AbstractCommand[GetToolsEnabledStatusInput, GetToolsEnabledStatusOutput]):
    def __init__(self, input_model: GetToolsEnabledStatusInput):
        super().__init__(input_model)
        self._original_config_data: Optional[_U2ASessionAgentConfig] = None

    async def execute(self) -> GetToolsEnabledStatusOutput:
        # 确定要查询的工具列表
        requested_tools: List[ToolNameEnum]
        if self.input_model.tool_names is None or len(self.input_model.tool_names) == 0:
            # 如果没有指定，获取所有工具
            requested_tools = list(ToolNameEnum)
        else:
            # 使用指定的工具名称
            requested_tools = self.input_model.tool_names
        
        # 加载配置
        config = await self.load_config(self.input_model.session_id)

        # 构建工具状态列表
        tools_status: List[ToolEnabledStatus] = []

        for tool_enum in requested_tools:
            tool_name_str = tool_enum.value
            # 只返回在配置中存在的工具
            if tool_name_str in config.tools_config:
                enabled = config.tools_config[tool_name_str].enabled
                tools_status.append(ToolEnabledStatus(
                    tool_name=tool_enum,
                    enabled=enabled
                ))
            # 如果工具不存在于配置中，则跳过，不返回该工具的信息

        return GetToolsEnabledStatusOutput(
            tools_status=tools_status,
            success=True
        )

    async def rollback(self) -> GetToolsEnabledStatusOutput:
        # 获取工具状态命令不需要回滚
        
        return GetToolsEnabledStatusOutput(
            tools_status=[],
            success=True,
            message="Get tools enabled status command doesn't need rollback"
        )

    async def load_config(self, session_id: str) -> SessionAgentConfig:
        # 从数据库加载配置
        try:
            # 尝试解析session_id为UUID
            session_uuid = UUID(session_id)
        except ValueError:
            # 如果不是有效的UUID格式，返回默认配置
            return SessionAgentConfig(version="v0.1")

        config_data = await get_session_config_by_session_id(session_uuid)

        if config_data:
            # 从数据库中的config字典创建SessionAgentConfig实例
            return SessionAgentConfig.model_validate(config_data.config)
        else:
            # 返回默认配置
            return SessionAgentConfig(version="v0.1")
