from uuid import UUID
from pathlib import Path
from typing import List

from api.user_space.file_system.path_utils import build_full_path
from api.user_space.file_system.fs_utils.open import open_file
from api.user_space.file_system.fs_utils.list import list_directory_contents
from .constant import DefaultConversationStrategies, DefaultConcludingGuidance

def get_user_agent_role_definition_path(user_id: UUID, role_name: str):
    return build_full_path(user_id, Path(f".agent_role_definitions/{role_name}/"))

def get_user_agent_role_conversation_strategies_path(user_id: UUID, role_name: str):
    role_def_folder = get_user_agent_role_definition_path(user_id, role_name)
    return build_full_path(user_id, role_def_folder / "conversation_strategies.md")

def user_agent_role_conversation_strategies_file(user_id: UUID, role_name: str, mode: str):
    file_path = get_user_agent_role_conversation_strategies_path(user_id, role_name)
    return open_file(user_id, file_path, mode)

def get_user_agent_role_concluding_guidence_path(user_id: UUID, role_name: str):
    role_def_folder = get_user_agent_role_definition_path(user_id, role_name)
    return build_full_path(user_id, role_def_folder / "concluding_guidance.md")

def user_agent_role_concluding_guidence_file(user_id: UUID, role_name: str, mode: str):
    file_path = get_user_agent_role_concluding_guidence_path(user_id, role_name)
    return open_file(user_id, file_path, mode)

def get_user_agent_role_strategies_update_cache_path(user_id: UUID, role_name: str):
    role_def_folder = get_user_agent_role_definition_path(user_id, role_name)
    return build_full_path(user_id, role_def_folder / "strategies_update_cache.json")

def user_agent_role_strategies_update_cache_file(user_id: UUID, role_name: str, mode: str):
    file_path = get_user_agent_role_strategies_update_cache_path(user_id, role_name)
    return open_file(user_id, file_path, mode)

async def list_available_agent_roles(user_id: UUID) -> List[str]:
    # 获取Agent角色定义目录
    agent_roles_dir = Path(".agent_role_definitions")

    # 列出目录内容
    items = await list_directory_contents(
        user_id=user_id,
        directory_path=agent_roles_dir,
        include_hidden=False
    )

    # 提取角色名称（目录名）
    role_names = []
    for item in items:
        # 只处理目录项
        if item.item_type == "folder":
            item_path = Path(item.file_path)
            # 提取目录名（即角色名称）
            role_name = item_path.name
            role_names.append(role_name)

    # 按字母顺序排序
    role_names.sort()
    return role_names


async def init_user_agent_role_definition_folder(user_id: UUID, role_name: str):
    conversation_strategies_file = user_agent_role_conversation_strategies_file(user_id, role_name, "w")
    async with conversation_strategies_file as f:
        f.seek(0)
        f.truncate(0)
        f.write(DefaultConversationStrategies.encode("utf-8"))
    concluding_guidence_file = user_agent_role_concluding_guidence_file(user_id, role_name, "w")
    async with concluding_guidence_file as f:
        f.seek(0)
        f.truncate(0)
        f.write(DefaultConcludingGuidance.encode("utf-8"))
    strategies_update_cache_file = user_agent_role_strategies_update_cache_file(user_id, role_name, "w")
    async with strategies_update_cache_file as f:
        f.seek(0)
        f.truncate(0)
        f.write("{}".encode("utf-8"))
