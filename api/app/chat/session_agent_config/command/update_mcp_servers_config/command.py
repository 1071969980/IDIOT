from typing import Optional
from uuid import UUID

from .data_model import (
    UpdateMcpServersConfigInput,
    UpdateMcpServersConfigOutput,
)
from ..base import AbstractCommand
from api.agent.sql_stat.u2a_session_agent_config.utils import (
    get_session_config_by_session_id,
    update_session_config_by_session_id,
    insert_session_config,
    session_config_exists_by_session_id,
    _U2ASessionAgentConfig,
    _U2ASessionAgentConfigCreate,
)
from api.agent.session_agent_config.config_data_model import SessionAgentConfig
from api.agent.tools.mcp.config_data_model import McpClientConfig


class UpdateMcpServersConfigCommand(AbstractCommand[UpdateMcpServersConfigInput, UpdateMcpServersConfigOutput]):
    def __init__(self, input_model: UpdateMcpServersConfigInput, session_id: str, user_id: str):
        super().__init__(input_model, session_id, user_id)
        self._original_config_data: Optional[_U2ASessionAgentConfig] = None
        self._session_uuid: Optional[UUID] = None

    async def execute(self) -> UpdateMcpServersConfigOutput:
        try:
            # 解析session_id为UUID
            self._session_uuid = UUID(self.session_id)
        except ValueError:
            return UpdateMcpServersConfigOutput(
                servers=[],
                success=False,
                message="Invalid session_id format"
            )

        # 加载现有配置，如果不存在则创建默认配置
        config = await self.load_config(self.session_id)

        # 保存原始配置用于回滚
        self._original_config_data = await get_session_config_by_session_id(self._session_uuid)

        # 如果 mcp_config 为 None，创建默认的 McpClientConfig
        if config.mcp_config is None:
            config.mcp_config = McpClientConfig(servers=self.input_model.servers)
        else:
            config.mcp_config.servers = self.input_model.servers
            
        # 保存更新后的配置到数据库
        await self.save_config(config)

        return UpdateMcpServersConfigOutput(
            servers=self.input_model.servers,
            success=True,
            message=f"Updated {len(self.input_model.servers)} MCP server(s)"
        )

    async def rollback(self) -> UpdateMcpServersConfigOutput:
        if self._original_config_data is None or self._session_uuid is None:
            return UpdateMcpServersConfigOutput(
                servers=[],
                success=True,
                message="No rollback needed - no changes were made"
            )

        try:
            # 恢复原始配置
            config_exists = await session_config_exists_by_session_id(self._session_uuid)

            if config_exists:
                await update_session_config_by_session_id(
                    self._session_uuid,
                    self._original_config_data.config
                )
            else:
                # 如果之前没有配置，删除新创建的配置
                from api.agent.sql_stat.u2a_session_agent_config.utils import delete_session_config_by_session_id
                await delete_session_config_by_session_id(self._session_uuid)

            # 获取回滚后的 servers 列表
            original_config = SessionAgentConfig.model_validate(self._original_config_data.config)
            servers = original_config.mcp_config.servers if original_config.mcp_config else []

            return UpdateMcpServersConfigOutput(
                servers=servers,
                success=True,
                message="Successfully rolled back changes"
            )
        except Exception as e:
            return UpdateMcpServersConfigOutput(
                servers=[],
                success=False,
                message=f"Rollback failed: {str(e)}"
            )

    async def load_config(self, session_id: str) -> SessionAgentConfig:
        """从数据库加载配置，如果不存在则创建默认配置"""
        try:
            session_uuid = UUID(session_id)
        except ValueError:
            return SessionAgentConfig()

        config_data = await get_session_config_by_session_id(session_uuid)

        if config_data:
            return SessionAgentConfig.model_validate(config_data.config)
        else:
            # 如果配置不存在，创建默认配置并保存到数据库
            default_config = SessionAgentConfig()
            self._session_uuid = session_uuid
            await self.save_config(default_config)
            return default_config

    async def save_config(self, config: SessionAgentConfig) -> None:
        """保存配置到数据库"""
        if self._session_uuid is None:
            return

        config_dict = config.model_dump()

        # 检查配置是否已存在
        config_exists = await session_config_exists_by_session_id(self._session_uuid)

        if config_exists:
            await update_session_config_by_session_id(self._session_uuid, config_dict)
        else:
            create_data = _U2ASessionAgentConfigCreate(
                session_id=self._session_uuid,
                config=config_dict
            )
            await insert_session_config(create_data)
