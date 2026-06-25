# api/agent/tools/sub_agent/definition_loader.py

"""子 agent 定义文件加载器。"""

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

import yaml
from loguru import logger

from api.agent.tools.mcp.config_data_model import McpClientConfig
from api.agent.tools.type import UserToolCallingPermissionRole
from api.user_pod_scheduler.constants import JUICEFS_MOUNT_PATH

from api.juiceFS.client_worker import get_worker_pool, Operation
from api.juiceFS.client_worker.models import SummaryEntry
from api.juiceFS.path_utils import get_meta_url, get_pvc_name, validate_and_build_path

AGENTS_DIR = PurePosixPath("sys/agents")


def _to_container_path(rel_path: str | PurePosixPath) -> str:
    """JuiceFS 相对路径 -> 用户容器绝对路径（/dist_fs/...）。"""
    rel = str(rel_path).lstrip("/")
    return str(PurePosixPath(JUICEFS_MOUNT_PATH) / rel) if rel else JUICEFS_MOUNT_PATH


def _resolve_disclosed_names(named_paths: list[tuple[str, str]]) -> list[str]:
    """根据 [(原始name, rel_path), ...] 计算等长的「披露名」列表。

    无重名的 name 保持原值；出现重名的 name 改用其容器绝对路径作为披露名。
    """
    counts = Counter(name for name, _ in named_paths)
    return [
        _to_container_path(rel) if counts[name] > 1 else name
        for name, rel in named_paths
    ]


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


def _build_agent_search_paths(
    role: UserToolCallingPermissionRole | None = None,
    search_paths: list[PurePosixPath] | None = None,
) -> list[PurePosixPath]:
    """根据角色和搜索路径构建 agent 定义搜索路径列表。

    Args:
        role: 用户角色，None 表示兼容模式（仅搜索 sys/agents）
        search_paths: 搜索路径列表

    Returns:
        搜索路径列表

    Raises:
        ValueError: 配置无效（VISITOR 无 search_paths、不支持的角色）
    """
    if role is None and not search_paths:
        return [AGENTS_DIR]

    if role not in (UserToolCallingPermissionRole.OWNER, UserToolCallingPermissionRole.VISITOR):
        raise ValueError("配置无效: sub_agent 不支持该角色")

    if role == UserToolCallingPermissionRole.VISITOR:
        if not search_paths:
            raise ValueError("配置无效: VISITOR 角色缺少 search_paths")
        return [p / "agents" for p in search_paths]

    # OWNER
    paths = [AGENTS_DIR]
    paths.extend(p / "agents" for p in (search_paths or []))
    return paths


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


async def load_user_agent_definitions(
    user_id: UUID,
    *,
    role: UserToolCallingPermissionRole | None = None,
    search_paths: list[PurePosixPath] | None = None,
) -> dict[str, SubAgentDefinition]:
    """加载用户空间的子 agent 定义。

    根据角色和搜索路径从多个目录加载 agent 定义文件。
    同名 agent 在多条搜索路径中出现时，按容器绝对路径重命名以消歧。

    Args:
        user_id: 用户 ID
        role: 用户角色
        search_paths: 搜索路径列表

    Returns:
        披露名（通常等于 agent 名，重名时为 /dist_fs/... 路径）到定义的映射字典

    Raises:
        ValueError: 单个定义文件解析失败时中止整个加载
    """
    collected: list[tuple[SubAgentDefinition, str]] = []  # (定义, .md 相对路径)

    pool = get_worker_pool()
    meta_url = get_meta_url(str(user_id))
    pvc_name = get_pvc_name(str(user_id))

    agent_search_paths = _build_agent_search_paths(role, search_paths)

    for search_root in agent_search_paths:
        # 构建安全路径
        try:
            safe_path = validate_and_build_path(str(search_root), pvc_name)
        except ValueError:
            continue

        # 使用 LISTTREE 一次性获取完整目录树
        try:
            result = await pool.call(
                meta_url, Operation.LISTTREE, safe_path,
                254,    # depth: 最大递归深度
                100000, # entries: 每层最大条目数
            )
        except Exception:
            continue

        # 从目录树中收集所有 .md 文件的相对路径
        skip_hidden = role == UserToolCallingPermissionRole.VISITOR
        md_paths = _collect_md_paths(result.summary, search_root, skip_hidden=skip_hidden)

        # 逐个读取并解析
        for rel_path in md_paths:
            try:
                file_safe_path = validate_and_build_path(rel_path, pvc_name)
                read_result = await pool.call(meta_url, Operation.READ, file_safe_path)
                content = read_result.content.decode("utf-8")
                definition = parse_definition_file(content)
            except ValueError:
                # 解析错误（坏文件）中止整个加载
                raise
            except Exception:
                continue
            collected.append((definition, rel_path))

    # 同名子代理按容器绝对路径重命名以消歧（仅重名时加前缀）
    disclosed = _resolve_disclosed_names([(d.name, rel) for d, rel in collected])

    results: dict[str, SubAgentDefinition] = {}
    for name, (definition, rel_path) in zip(disclosed, collected):
        if name in results:
            logger.warning("子代理披露名重复，跳过后者: name={}, path={}", name, rel_path)
            continue
        results[name] = definition

    return results


def _collect_md_paths(summary: SummaryEntry, root_dir: PurePosixPath, *, skip_hidden: bool = False) -> list[str]:
    """从 SummaryEntry 树中收集所有 .md 文件的相对路径。

    Args:
        summary: LISTTREE 返回的目录树根节点
        root_dir: 根目录
        skip_hidden: 是否跳过含隐藏组件的路径（以 . 开头的目录）

    Returns:
        相对路径列表
    """
    paths = []
    stack = list(summary.Children or [])
    while stack:
        current = stack.pop()
        if skip_hidden and _has_hidden_component(current.Path):
            continue
        if current.Type == "regular" and current.Path.endswith(".md"):
            paths.append(str(root_dir / current.Path))
        if current.Children:
            stack.extend(current.Children)
    return paths


def _has_hidden_component(path: str) -> bool:
    """检查路径中是否有组件以 . 开头。"""
    return any(part.startswith(".") for part in PurePosixPath(path).parts)
