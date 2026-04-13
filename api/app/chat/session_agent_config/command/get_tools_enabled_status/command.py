from typing import List, Optional
from uuid import UUID

from api.agent.session_agent_config.config_data_model import SessionAgentConfig, DEFAULT_MAIN_AGENT_TOOLS_CONFIG
from api.agent.sql_stat.u2a_session_agent_config.utils import (
    _U2ASessionAgentConfig,
    _U2ASessionAgentConfigCreate,
    get_session_config_by_session_id,
    insert_session_config,
    session_config_exists_by_session_id,
    update_session_config_by_session_id,
)

from ..base import AbstractCommand
from .data_model import GetToolsEnabledStatusInput, GetToolsEnabledStatusOutput, ToolEnabledStatus, ToolNameEnum


class GetToolsEnabledStatusCommand(AbstractCommand[GetToolsEnabledStatusInput, GetToolsEnabledStatusOutput]):
    """
    get_tools_enabled_status 命令具有以下行为：
    1. 如果配置不存在，则创建默认配置并保存到数据库；然后返回默认配置中的工具状态
    2. 如果配置已存在，验证其是否为非法结构，则用默认配置的工具配置的部分替换已存在的工具配置，并保存到数据库；然后返回默认配置中的工具状态
    3. 如果配置已存在，且为合法结构，忠实地返回工具状态

    合法结构的判断：工具配置 tools_config 部分的键名应该和 ToolNameEnum 完全一致，数量不多不少，字符一致。

    使用默认配置前，需要确保其为合法结构，如果默认配置不是合法结构，应当直接抛出异常（通常是因为修改了默认配置，但是忘了修改 ToolNameEnum 枚举）。
    """

    def __init__(self, input_model: GetToolsEnabledStatusInput, session_id: str, user_id: str):
        super().__init__(input_model, session_id, user_id)
        self._original_config_data: Optional[_U2ASessionAgentConfig] = None
        self._session_uuid: Optional[UUID] = None

    @classmethod
    def _validate_default_config(cls) -> None:
        """验证默认配置是否为合法结构，如果不合法则抛出异常"""
        expected_tool_names = {tool_enum.value for tool_enum in ToolNameEnum}
        default_tool_names = set(DEFAULT_MAIN_AGENT_TOOLS_CONFIG.keys())

        if expected_tool_names != default_tool_names:
            missing_in_default = expected_tool_names - default_tool_names
            extra_in_default = default_tool_names - expected_tool_names
            error_msg = "DEFAULT_TOOLS_CONFIG structure is invalid. "
            if missing_in_default:
                error_msg += f"Missing tools: {missing_in_default}. "
            if extra_in_default:
                error_msg += f"Extra tools: {extra_in_default}. "
            error_msg += "Please sync DEFAULT_TOOLS_CONFIG with ToolNameEnum."
            raise ValueError(error_msg)

    @classmethod
    def _is_valid_config_structure(cls, config: SessionAgentConfig) -> bool:
        """检查配置是否为合法结构"""
        expected_tool_names = {tool_enum.value for tool_enum in ToolNameEnum}
        actual_tool_names = set(config.tools_config.keys())
        return expected_tool_names == actual_tool_names

    @classmethod
    def _fix_config_structure(cls, config: SessionAgentConfig) -> SessionAgentConfig:
        """用默认配置的工具配置部分替换配置中的工具配置"""
        config.tools_config = {k: v.model_copy() for k, v in DEFAULT_MAIN_AGENT_TOOLS_CONFIG.items()}
        return config

    async def execute(self) -> GetToolsEnabledStatusOutput:
        # 验证默认配置结构是否合法
        self._validate_default_config()

        # 确定要查询的工具列表
        requested_tools: List[ToolNameEnum]
        if self.input_model.tool_names is None or len(self.input_model.tool_names) == 0:
            # 如果没有指定，获取所有工具
            requested_tools = list(ToolNameEnum)
        else:
            # 使用指定的工具名称
            requested_tools = self.input_model.tool_names

        # 加载配置（会处理配置不存在或结构非法的情况）
        config = await self.load_config(self.session_id)

        # 构建工具状态列表
        tools_status: List[ToolEnabledStatus] = []

        for tool_enum in requested_tools:
            tool_name_str = tool_enum.value
            if tool_name_str in config.tools_config:
                enabled = config.tools_config[tool_name_str].enabled
                tools_status.append(ToolEnabledStatus(
                    tool_name=tool_enum,
                    enabled=enabled
                ))

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
        """从数据库加载配置，如果不存在则创建默认配置，如果结构非法则修复"""
        # 验证默认配置结构是否合法
        self._validate_default_config()

        try:
            session_uuid = UUID(session_id)
        except ValueError:
            # 如果不是有效的UUID格式，返回默认配置
            return SessionAgentConfig()

        self._session_uuid = session_uuid
        config_data = await get_session_config_by_session_id(session_uuid)

        if config_data:
            # 从数据库中的config字典创建SessionAgentConfig实例
            config = SessionAgentConfig.model_validate(config_data.config)

            # 检查配置结构是否合法
            if not self._is_valid_config_structure(config):
                # 结构非法，用默认配置的工具配置部分替换
                config = self._fix_config_structure(config)
                # 保存修复后的配置
                await self.save_config(config)

            return config
        else:
            # 配置不存在，创建默认配置并保存到数据库
            default_config = SessionAgentConfig()
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
