"""
Session Agent Config 读写辅助函数

提供对 session_agent_config 的统一读写接口，支持基础配置 + storage_snapshot overlay 层的
合并读写范式。大部分情况下，不直接修改 session_agent_config 表，而是通过修改 task 中
storage_snapshot 的 session_config_overlay 字段来实现功能。

注意：本模块不负责解析 branch_name 到 task_id，该逻辑由调用方（通常是 command 实现）处理。
"""

from uuid import UUID

from api.agent.session_agent_config.config_data_model import SessionAgentConfig
from api.agent.session_agent_config.constants import (
    SESSION_CONFIG_OVERLAY_KEY_IN_TASK_STORAGE_SNAPSHOT,
)
from api.agent.sql_stat.u2a_session_agent_config.utils import (
    get_session_config_by_session_id,
)
from api.chat.sql_stat.u2a_session_task.utils import (
    update_task_storage_snapshot,
)


def deep_update_dict(original: dict, update_with: dict) -> dict:
    """
    递归地将 update_with 中的内容合并到 original 字典中。
    对于嵌套的字典会进行深度合并，其余类型直接覆盖。

    注意：该函数会就地修改 original 字典，并返回它。
    """
    for key, value in update_with.items():
        if isinstance(value, dict) and isinstance(original.get(key), dict):
            deep_update_dict(original[key], value)
        else:
            original[key] = value
    return original


async def get_base_session_config(session_id: UUID) -> SessionAgentConfig:
    """从 u2a_session_agent_config 表中获取基础会话配置。

    Args:
        session_id: 会话 UUID

    Returns:
        SessionAgentConfig 实例

    Raises:
        ValueError: 当配置不存在时
    """
    session_config_row = await get_session_config_by_session_id(session_id)
    if session_config_row is None:
        raise ValueError(f"Session config not found for session {session_id}")
    return SessionAgentConfig.model_validate(session_config_row.config)


def get_effective_session_config(
    base_config: SessionAgentConfig,
    storage_snapshot: dict | None = None,
) -> SessionAgentConfig:
    """获取有效配置（基础配置 + overlay 合并）。

    Args:
        base_config: 基础配置
        storage_snapshot: 任务的 storage_snapshot 字典。为 None 时直接返回基础配置。

    Returns:
        合并后的 SessionAgentConfig 实例
    """
    if storage_snapshot is None:
        return base_config

    if SESSION_CONFIG_OVERLAY_KEY_IN_TASK_STORAGE_SNAPSHOT in storage_snapshot:
        overlay = storage_snapshot.get(SESSION_CONFIG_OVERLAY_KEY_IN_TASK_STORAGE_SNAPSHOT, {})
        if not isinstance(overlay, dict):
            raise ValueError(f"{SESSION_CONFIG_OVERLAY_KEY_IN_TASK_STORAGE_SNAPSHOT} has invalid type")
        merged = deep_update_dict(
            base_config.model_dump(mode="json"),
            overlay,
        )
        return SessionAgentConfig.model_validate(merged)

    return base_config


async def update_config_overlay(
    task_id: UUID,
    storage_snapshot: dict,
    overlay_updates: dict,
) -> dict:
    """将 overlay_updates 深度合并到 storage_snapshot 的 overlay 中，并持久化。

    不会替换整个 overlay，而是将 overlay_updates 合并到已存在的 overlay 中。

    Args:
        task_id: 任务 UUID
        storage_snapshot: 任务的 storage_snapshot 字典（会被就地修改）
        overlay_updates: 要合并的 overlay 字典片段

    Returns:
        更新后的 storage_snapshot
    """
    existing_overlay = storage_snapshot.get(SESSION_CONFIG_OVERLAY_KEY_IN_TASK_STORAGE_SNAPSHOT, {})
    if existing_overlay is None:
        existing_overlay = {}

    merged_overlay = deep_update_dict(existing_overlay, overlay_updates)

    storage_snapshot[SESSION_CONFIG_OVERLAY_KEY_IN_TASK_STORAGE_SNAPSHOT] = merged_overlay
    await update_task_storage_snapshot(task_id, storage_snapshot)

    return storage_snapshot
