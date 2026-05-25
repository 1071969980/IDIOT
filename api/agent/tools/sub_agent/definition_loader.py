# api/agent/tools/sub_agent/definition_loader.py

"""子 agent 定义文件加载器。"""

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from uuid import UUID

import yaml

from api.agent.tools.mcp.config_data_model import McpClientConfig

from api.juiceFS.client_worker import get_worker_pool, Operation
from api.juiceFS.client_worker.models import SummaryEntry
from api.juiceFS.path_utils import get_meta_url, get_pvc_name, validate_and_build_path


@dataclass
class SubAgentDefinition:
    """子 agent 定义数据类。"""

    name: str
    description: str
    tools: list[str]
    mcp_server_config: McpClientConfig | None
    system_prompt: str  # markdown 正文
    skills: list[str] = field(default_factory=list)  # 子代理应加载的技能列表
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


async def load_user_agent_definitions(user_id: UUID) -> dict[str, SubAgentDefinition]:
    """加载用户空间的子 agent 定义。

    从用户 JuiceFS 文件系统的 sys/agents/ 目录递归加载所有 .md 文件。
    使用 LISTTREE 一次获取完整目录树，避免多次递归 IPC 调用。

    Args:
        user_id: 用户 ID

    Returns:
        agent 名称到定义的映射字典
    """
    definitions = {}

    pool = get_worker_pool()
    meta_url = get_meta_url(str(user_id))
    pvc_name = get_pvc_name(str(user_id))

    agents_dir = PurePosixPath("sys/agents")

    # 构建安全路径
    try:
        safe_path = validate_and_build_path(str(agents_dir), pvc_name)
    except ValueError:
        return definitions

    # 使用 LISTTREE 一次性获取完整目录树
    try:
        result = await pool.call(
            meta_url, Operation.LISTTREE, safe_path,
            254,   # depth: 最大递归深度
            100000,  # entries: 每层最大条目数
        )
    except Exception:
        return definitions

    # 从目录树中收集所有 .md 文件的相对路径
    md_paths = _collect_md_paths(result.summary, agents_dir)

    # 逐个读取并解析
    for rel_path in md_paths:
        try:
            file_safe_path = validate_and_build_path(rel_path, pvc_name)
            read_result = await pool.call(meta_url, Operation.READ, file_safe_path)
            content = read_result.content.decode("utf-8")
            definition = parse_definition_file(content)
            definitions[definition.name] = definition
        except Exception:
            continue

    return definitions


def _collect_md_paths(summary: SummaryEntry, root_dir: PurePosixPath) -> list[str]:
    """从 SummaryEntry 树中收集所有 .md 文件的相对路径。

    Args:
        summary: LISTTREE 返回的目录树根节点（路径已标准化为相对路径）
        root_dir: 根目录（如 PurePosixPath("sys/agents")）

    Returns:
        相对路径列表（如 ["sys/agents/my_agent.md", "sys/agents/sub/other.md"]）
    """
    paths = []
    stack = list(summary.Children or [])
    while stack:
        current = stack.pop()
        if current.Type == "regular" and current.Path.endswith(".md"):
            paths.append(str(root_dir / current.Path))
        if current.Children:
            stack.extend(current.Children)
    return paths
