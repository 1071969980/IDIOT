# api/agent/tools/sub_agent/definition_loader.py

"""子 agent 定义文件加载器。"""

import re
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import yaml

from api.agent.tools.mcp.config_data_model import McpClientConfig

from api.user_space.file_system.fs_utils.list import list_directory_contents
from api.user_space.file_system.fs_utils.open import open_file
from api.user_space.file_system.sql_stat.utils import _FileSystemItem


@dataclass
class SubAgentDefinition:
    """子 agent 定义数据类。"""

    name: str
    description: str
    tools: list[str]
    mcp_server_config: McpClientConfig | None
    system_prompt: str  # markdown 正文


def parse_definition_file(content: str) -> SubAgentDefinition:
    """解析子 agent 定义文件。

    文件格式：
    ---
    name: agent_name
    description: 描述
    tools: [...]
    mcp_server_config: {...}
    ---

    系统提示词正文

    Args:
        content: 定义文件的完整内容

    Returns:
        解析后的 AgentDefinition 对象

    Raises:
        ValueError: 如果文件格式无效或缺少必需字段
    """
    # 分离 YAML frontmatter 和 markdown 正文
    match = re.match(r'^---\n(.*?)\n---\n(.*)$', content, re.DOTALL)
    if not match:
        raise ValueError("无效的定义文件格式：缺少 YAML frontmatter")

    frontmatter_yaml = match.group(1)
    system_prompt = match.group(2).strip()

    # 解析 YAML
    try:
        metadata = yaml.safe_load(frontmatter_yaml)
    except yaml.YAMLError as e:
        raise ValueError(f"YAML 解析失败：{e}")

    # 验证必需字段
    if "name" not in metadata or "description" not in metadata:
        raise ValueError("定义文件缺少必需字段：name 或 description")

    # 解析 MCP 配置（如果存在）
    mcp_config = None
    if "mcp_server_config" in metadata:
        try:
            mcp_config = McpClientConfig(**metadata["mcp_server_config"])
        except Exception as e:
            raise ValueError(f"MCP 配置解析失败：{e}")

    return SubAgentDefinition(
        name=metadata["name"],
        description=metadata["description"],
        tools=metadata.get("tools", []),
        mcp_server_config=mcp_config,
        system_prompt=system_prompt,
    )

async def load_system_agent_definitions() -> dict[str, SubAgentDefinition]:
    """加载系统内置的子 agent 定义。

    从静态定义文件目录 (default_agent_def/) 加载。

    Returns:
        agent 名称到定义的映射字典
    """
    definitions = {}

    static_dir = Path(__file__).parent / "default_agent_def"
    for md_file in static_dir.glob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            definition = parse_definition_file(content)
            definitions[definition.name] = definition
        except Exception:
            # 跳过无法解析的文件
            continue

    return definitions


async def load_user_agent_definitions(user_id: UUID) -> dict[str, SubAgentDefinition]:
    """加载用户空间的子 agent 定义。

    从用户空间文件系统的 .sub_agent_def/ 目录加载。

    Args:
        user_id: 用户 ID

    Returns:
        agent 名称到定义的映射字典
    """
    definitions = {}

    user_space_dir = Path(f".sub_agent_def")
    items = await list_directory_contents(
        user_id,
        user_space_dir,
        allow_hidden_path_part=True,
    )
    user_space_md_files: list[_FileSystemItem] = []
    for item in items:
        if item.item_type == "file" and item.file_path.endswith(".md"):
            user_space_md_files.append(item)

    for md_file in user_space_md_files:
        try:
            async with open_file(user_id, Path(md_file.file_path), "r", create_if_missing=False) as f:
                content = f.read().decode("utf-8")
                definition = parse_definition_file(content)
                definitions[definition.name] = definition
        except Exception:
            # 跳过无法解析的文件
            continue

    return definitions


async def load_all_agent_definitions(user_id: UUID) -> dict[str, SubAgentDefinition]:
    """加载所有可用的子 agent 定义。

    加载顺序：
    1. 系统内置定义（default_agent_def/）
    2. 用户空间定义（用户空间文件系统）

    用户空间定义会覆盖同名系统定义。

    Args:
        user_id: 用户 ID

    Returns:
        agent 名称到定义的映射字典
    """
    # 加载系统定义
    definitions = await load_system_agent_definitions()

    # 加载用户定义并合并（用户定义覆盖系统定义）
    user_definitions = await load_user_agent_definitions(user_id)
    definitions.update(user_definitions)

    return definitions
