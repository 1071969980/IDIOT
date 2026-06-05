# api/agent/tools/sub_agent/definition_loader.py

"""子 agent 定义文件加载器。"""

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any
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


def _normalize_list_field(value: Any, field_name: str) -> list[str]:
    """将 YAML 中可能是多种格式的列表字段统一为 list[str]。"""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()]
    raise ValueError(f"字段 '{field_name}' 应为列表，实际类型：{type(value).__name__}")


def _validate_hook_path(raw: str) -> PurePosixPath:
    """校验 before_agent_start_hook 路径合法性。"""
    if not raw or not raw.strip():
        raise ValueError("before_agent_start_hook 不能为空字符串")
    path = PurePosixPath(raw.strip())
    if path.is_absolute():
        return path
    raise ValueError(f"before_agent_start_hook 必须为绝对路径，实际值：{raw}")


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
    if not content or not content.strip():
        raise ValueError("定义文件内容为空")

    # 前导空白，统一换行符
    cleaned = content.strip().replace("\r\n", "\n")

    # 分离 YAML frontmatter 和 markdown 正文
    match = re.match(r'^---\n(.*?)\n---\n(.*)$', cleaned, re.DOTALL)
    if not match:
        raise ValueError("无效的定义文件格式：缺少 YAML frontmatter（需以 --- 开头和结尾）")

    frontmatter_yaml = match.group(1)
    system_prompt = match.group(2).strip()

    # 解析 YAML
    try:
        metadata = yaml.safe_load(frontmatter_yaml)
    except yaml.YAMLError as e:
        raise ValueError(f"YAML 解析失败：{e}")

    if not isinstance(metadata, dict):
        raise ValueError(f"YAML frontmatter 应为键值对映射，实际类型：{type(metadata).__name__}")

    # 验证必需字段
    name = metadata.get("name")
    description = metadata.get("description")
    if not name or not isinstance(name, str):
        raise ValueError("定义文件缺少必需字段 'name'，或 name 不是有效字符串")
    if not description or not isinstance(description, str):
        raise ValueError("定义文件缺少必需字段 'description'，或 description 不是有效字符串")

    # 解析列表字段（兼容逗号分隔字符串写法）
    tools = _normalize_list_field(metadata.get("tools"), "tools")
    skills = _normalize_list_field(metadata.get("skills"), "skills")

    # 解析 MCP 配置（存在且非 null 时才解析）
    mcp_config = None
    raw_mcp = metadata.get("mcp_server_config")
    if raw_mcp is not None:
        try:
            mcp_config = McpClientConfig(**raw_mcp)
        except Exception as e:
            raise ValueError(f"MCP 配置解析失败：{e}")

    # 解析 before_agent_start_hook
    raw_hook = metadata.get("before_agent_start_hook")
    hook_path = _validate_hook_path(raw_hook) if raw_hook else None

    return SubAgentDefinition(
        name=name.strip(),
        description=description.strip(),
        tools=tools,
        mcp_server_config=mcp_config,
        system_prompt=system_prompt,
        skills=skills,
        default_context_mode=metadata.get("default_context_mode", "standalone"),
        default_should_feedback=metadata.get("default_should_feedback", True),
        disable_completion_callback=metadata.get("disable_completion_callback", False),
        service=metadata.get("service", None),
        before_agent_start_hook=hook_path,
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
