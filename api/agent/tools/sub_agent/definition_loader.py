# api/agent/tools/sub_agent/definition_loader.py

"""子 agent 定义文件加载器。"""

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import UUID

import yaml

from api.agent.tools.mcp.config_data_model import McpClientConfig

from api.juiceFS.client_worker import get_worker_pool, Operation
from api.juiceFS.client_worker.models import FileInfo
from api.juiceFS.path_utils import get_meta_url, get_pvc_name, validate_and_build_path


@dataclass
class SubAgentDefinition:
    """子 agent 定义数据类。"""

    name: str
    description: str
    tools: list[str]
    mcp_server_config: McpClientConfig | None
    system_prompt: str  # markdown 正文
    skills: list[str] = []  # 子代理应加载的技能列表
    default_context_mode: str = "standalone"  # 默认上下文模式
    default_should_feedback: bool = True  # 默认是否启用反馈
    disable_completion_callback: bool = False
    service: str | None = None  # LLM 服务名
    before_agent_start_hook: PurePosixPath | None = None  # 子代理启动前在用户容器中执行的脚本路径


def parse_definition_file(content: str) -> SubAgentDefinition:
    """解析子 agent 定义文件。

    文件格式：
    ---
    name: agent_name
    description: 描述
    tools: [...]
    skills: [...]
    default_context_mode: standalone
    default_should_feedback: true
    service: null
    mcp_server_config: {...}
    before_agent_start_hook: /path/to/script.sh
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
        skills=metadata.get("skills", []),
        default_context_mode=metadata.get("default_context_mode", "standalone"),
        default_should_feedback=metadata.get("default_should_feedback", True),
        disable_completion_callback=metadata.get("disable_completion_callback", False),
        service=metadata.get("service", None),
        before_agent_start_hook=(
            PurePosixPath(metadata["before_agent_start_hook"])
            if metadata.get("before_agent_start_hook") else None
        ),
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

    从用户 JuiceFS 文件系统的 sys/agents/ 目录加载。

    Args:
        user_id: 用户 ID

    Returns:
        agent 名称到定义的映射字典
    """
    definitions = {}

    pool = get_worker_pool()
    meta_url = get_meta_url(str(user_id))
    pvc_name = get_pvc_name(str(user_id))

    agents_dir = "sys/agents"

    # 构建安全路径
    try:
        safe_path = validate_and_build_path(agents_dir, pvc_name)
    except ValueError:
        return definitions

    # 列出目录内容
    try:
        result = await pool.call(meta_url, Operation.LISTDIR, safe_path, True)
    except Exception:
        return definitions

    # 筛选 .md 文件并读取
    for entry in result.entries:
        if isinstance(entry, FileInfo) and entry.name.endswith(".md"):
            try:
                file_path = f"{agents_dir}/{entry.name}"
                file_safe_path = validate_and_build_path(file_path, pvc_name)
                read_result = await pool.call(meta_url, Operation.READ, file_safe_path)
                content = read_result.content.decode("utf-8")
                definition = parse_definition_file(content)
                definitions[definition.name] = definition
            except Exception:
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
