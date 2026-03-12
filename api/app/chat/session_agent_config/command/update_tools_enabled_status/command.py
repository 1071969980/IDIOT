from typing import List, Optional
from .data_model import (
    UpdateToolsEnabledStatusInput,
    UpdateToolsEnabledStatusOutput,
    ToolEnabledStatus,
)
from ..get_tools_enabled_status.data_model import ToolNameEnum
from ..base import AbstractCommand
from api.agent.sql_stat.u2a_session_agent_config.utils import (
    get_session_config_by_session_id,
    update_session_config_by_session_id,
    _U2ASessionAgentConfig,
)
from api.agent.session_agent_config.config_data_model import SessionAgentConfig
from uuid import UUID


class UpdateToolsEnabledStatusCommand(AbstractCommand[UpdateToolsEnabledStatusInput, UpdateToolsEnabledStatusOutput]):
    """
    update_tools_enabled_status 命令具有以下行为：
    1. 如果当前配置不存在，则返回错误
    2. 如果当前配置存在，则更新配置。对于每个工具，如果工具在当前配置中不存在，返回错误。
    """
    
    def __init__(self, input_model: UpdateToolsEnabledStatusInput, session_id: str, user_id: str):
        super().__init__(input_model, session_id, user_id)
        self._original_config_data: Optional[_U2ASessionAgentConfig] = None
        self._session_uuid: Optional[UUID] = None

    async def execute(self) -> UpdateToolsEnabledStatusOutput:
        try:
            # 解析session_id为UUID
            self._session_uuid = UUID(self.session_id)
        except ValueError:
            return UpdateToolsEnabledStatusOutput(
                updated_tools=[],
                success=False,
                message="Invalid session_id format"
            )

        # 加载现有配置，如果不存在则返回错误
        config = await self.load_config(self.session_id)
        if config is None:
            return UpdateToolsEnabledStatusOutput(
                updated_tools=[],
                success=False,
                message=f"Session config not found for session_id: {self.session_id}"
            )

        # 保存原始配置用于回滚
        self._original_config_data = await get_session_config_by_session_id(self._session_uuid)

        # 构建可用工具名称集合 - 基于 Get 命令中的 ToolNameEnum 列表
        available_tool_names = {tool_enum.value for tool_enum in ToolNameEnum}

        # 验证所有要更新的工具是否都在允许的列表中
        for tool_status in self.input_model.tools_status:
            tool_name_str = tool_status.tool_name.value
            if tool_name_str not in available_tool_names:
                return UpdateToolsEnabledStatusOutput(
                    updated_tools=[],
                    success=False,
                    message=f"Tool '{tool_name_str}' is not a valid tool"
                )

        # 遍历要更新的工具状态
        updated_tools: List[ToolEnabledStatus] = []

        for tool_status in self.input_model.tools_status:
            tool_name_str = tool_status.tool_name.value

            # 如果工具在当前配置中不存在，返回错误
            if tool_name_str not in config.tools_config:
                return UpdateToolsEnabledStatusOutput(
                    updated_tools=[],
                    success=False,
                    message=f"Tool '{tool_name_str}' not found in configuration"
                )

            # 更新enabled状态
            config.tools_config[tool_name_str].enabled = tool_status.enabled
            updated_tools.append(tool_status)

        # 保存更新后的配置到数据库
        await self.save_config(config)

        return UpdateToolsEnabledStatusOutput(
            updated_tools=updated_tools,
            success=True,
            message=f"Updated {len(updated_tools)} tool(s)"
        )

    async def rollback(self) -> UpdateToolsEnabledStatusOutput:
        if self._original_config_data is None or self._session_uuid is None:
            return UpdateToolsEnabledStatusOutput(
                updated_tools=[],
                success=True,
                message="No rollback needed - no changes were made"
            )

        try:
            # 恢复原始配置
            await update_session_config_by_session_id(
                self._session_uuid,
                self._original_config_data.config
            )

            return UpdateToolsEnabledStatusOutput(
                updated_tools=[],
                success=True,
                message="Successfully rolled back changes"
            )
        except Exception as e:
            return UpdateToolsEnabledStatusOutput(
                updated_tools=[],
                success=False,
                message=f"Rollback failed: {str(e)}"
            )

    async def load_config(self, session_id: str) -> Optional[SessionAgentConfig]:
        """从数据库加载配置，如果不存在则返回 None"""
        try:
            session_uuid = UUID(session_id)
        except ValueError:
            return None

        config_data = await get_session_config_by_session_id(session_uuid)

        if config_data:
            return SessionAgentConfig.model_validate(config_data.config)
        else:
            return None

    async def save_config(self, config: SessionAgentConfig) -> None:
        """保存配置到数据库（配置必须已存在）"""
        if self._session_uuid is None:
            return

        config_dict = config.model_dump()
        await update_session_config_by_session_id(self._session_uuid, config_dict)
