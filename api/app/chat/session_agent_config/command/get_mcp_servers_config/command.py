from typing import Optional
from uuid import UUID

from api.agent.session_agent_config.config_data_model import SessionAgentConfig
from api.agent.sql_stat.u2a_session_agent_config.utils import (
    _U2ASessionAgentConfig,
    _U2ASessionAgentConfigCreate,
    get_session_config_by_session_id,
    insert_session_config,
    session_config_exists_by_session_id,
    update_session_config_by_session_id,
)

from ..base import AbstractCommand
from .data_model import GetMcpServersConfigInput, GetMcpServersConfigOutput


class GetMcpServersConfigCommand(AbstractCommand[GetMcpServersConfigInput, GetMcpServersConfigOutput]):
    def __init__(self, input_model: GetMcpServersConfigInput):
        super().__init__(input_model)
        self._original_config_data: Optional[_U2ASessionAgentConfig] = None
        self._session_uuid: Optional[UUID] = None

    async def execute(self) -> GetMcpServersConfigOutput:
        # 加载配置
        config = await self.load_config(self.input_model.session_id)

        # 返回 servers 列表，如果 mcp_config 为 None 则返回空列表
        servers = config.mcp_config.servers if config.mcp_config else []

        return GetMcpServersConfigOutput(
            servers=servers,
            success=True
        )

    async def rollback(self) -> GetMcpServersConfigOutput:
        # 获取 MCP servers 配置命令不需要回滚
        return GetMcpServersConfigOutput(
            servers=[],
            success=True,
            message="Get MCP servers config command doesn't need rollback"
        )

    async def load_config(self, session_id: str) -> SessionAgentConfig:
        # 从数据库加载配置
        try:
            # 尝试解析session_id为UUID
            session_uuid = UUID(session_id)
        except ValueError:
            # 如果不是有效的UUID格式，返回默认配置
            return SessionAgentConfig()

        config_data = await get_session_config_by_session_id(session_uuid)

        if config_data:
            # 从数据库中的config字典创建SessionAgentConfig实例
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
