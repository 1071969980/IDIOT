from uuid import UUID
from pathlib import Path
from typing import List, TYPE_CHECKING

from api.user_space.file_system.path_utils import build_full_path
from api.user_space.file_system.fs_utils.open import open_file
from api.user_space.file_system.fs_utils.list import list_directory_contents
from .constant import DefaultConversationStrategies, DefaultConcludingGuidance

if TYPE_CHECKING:
    from .storage_backend.base import AgentRoleStorageBackend

# ============ 保留原有路径函数（向后兼容） ============
def get_user_agent_role_definition_path(user_id: UUID, role_name: str):
    return build_full_path(user_id, Path(f".agent_role_definitions/{role_name}/"))


def get_user_agent_role_conversation_strategies_path(user_id: UUID, role_name: str):
    role_def_folder = get_user_agent_role_definition_path(user_id, role_name)
    return build_full_path(user_id, role_def_folder / "conversation_strategies.md")


def get_user_agent_role_concluding_guidence_path(user_id: UUID, role_name: str):
    role_def_folder = get_user_agent_role_definition_path(user_id, role_name)
    return build_full_path(user_id, role_def_folder / "concluding_guidance.md")


def get_user_agent_role_strategies_update_cache_path(user_id: UUID, role_name: str):
    role_def_folder = get_user_agent_role_definition_path(user_id, role_name)
    return build_full_path(user_id, role_def_folder / "strategies_update_cache.json")


# ============ 改造为使用存储后端（通过参数传递） ============

def user_agent_role_conversation_strategies_file(
    user_id: UUID,
    role_name: str,
    mode: str,
    storage_backend: "AgentRoleStorageBackend"
):
    """打开对话策略文件

    Args:
        user_id: 用户 ID
        role_name: 角色名称
        mode: 文件打开模式
        storage_backend: 存储后端实例

    Returns:
        异步文件对象上下文管理器
    """
    return storage_backend.open_conversation_strategies(role_name, mode)


def user_agent_role_concluding_guidence_file(
    user_id: UUID,
    role_name: str,
    mode: str,
    storage_backend: "AgentRoleStorageBackend"
):
    """打开总结引导文件

    Args:
        user_id: 用户 ID
        role_name: 角色名称
        mode: 文件打开模式
        storage_backend: 存储后端实例

    Returns:
        异步文件对象上下文管理器
    """
    return storage_backend.open_concluding_guidance(role_name, mode)


def user_agent_role_strategies_update_cache_file(
    user_id: UUID,
    role_name: str,
    mode: str,
    storage_backend: "AgentRoleStorageBackend"
):
    """打开更新缓存文件

    Args:
        user_id: 用户 ID
        role_name: 角色名称
        mode: 文件打开模式
        storage_backend: 存储后端实例

    Returns:
        异步文件对象上下文管理器
    """
    return storage_backend.open_strategies_update_cache(role_name, mode)


async def list_available_agent_roles(
    user_id: UUID,
    storage_backend: "AgentRoleStorageBackend"
) -> List[str]:
    """列出所有角色

    Args:
        user_id: 用户 ID
        storage_backend: 存储后端实例

    Returns:
        角色名称列表，按字母顺序排序
    """
    return await storage_backend.list_roles()


async def init_user_agent_role_definition_folder(
    user_id: UUID,
    role_name: str,
    storage_backend: "AgentRoleStorageBackend"
):
    """初始化角色目录

    Args:
        user_id: 用户 ID
        role_name: 角色名称
        storage_backend: 存储后端实例
    """
    await storage_backend.initialize_role(
        role_name,
        DefaultConversationStrategies,
        DefaultConcludingGuidance
    )
