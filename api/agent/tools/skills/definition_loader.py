# api/agent/tools/skills/definition_loader.py

"""Skill 定义加载器，从 JuiceFS 加载 skill 信息。"""

import re
import stat
from pathlib import PurePosixPath
from uuid import UUID

import yaml

from api.juiceFS.client_worker import Operation, get_worker_pool
from api.juiceFS.client_worker.models import SummaryEntry
from api.juiceFS.path_utils import get_meta_url, get_pvc_name, validate_and_build_path
from api.juiceFS.client_worker.pool import JuiceFSWorkerPool

from api.agent.tools.type import UserToolCallingPermissionRole

from .data_model import SkillDefinition, SkillInfo
from .load_skill.config_data_model import SkillConflictError


SKILLS_DIR = PurePosixPath("sys/skills")
SKILL_MD_FILENAME = "SKILL.md"


def _build_search_paths(
    role: UserToolCallingPermissionRole | None = None,
    proj_paths: list[PurePosixPath] | None = None,
) -> list[PurePosixPath]:
    """根据角色和项目路径构建技能搜索路径列表。

    Args:
        role: 用户角色，None 表示兼容模式（仅搜索 sys/skills）
        proj_paths: 项目路径列表，直接追加 /skills 后缀作为搜索路径

    Returns:
        搜索路径列表

    Raises:
        ValueError: 配置无效（VISITOR 无 proj_paths、不支持的角色）
    """
    if role is None and not proj_paths:
        return [SKILLS_DIR]

    if role not in (UserToolCallingPermissionRole.OWNER, UserToolCallingPermissionRole.VISITOR):
        raise ValueError("配置无效: load_skill 不支持该角色")

    if role == UserToolCallingPermissionRole.VISITOR:
        if not proj_paths:
            raise ValueError("配置无效: VISITOR 角色缺少 proj_paths")
        return [p / "skills" for p in proj_paths]

    # OWNER
    paths = [SKILLS_DIR]
    paths.extend(p / "skills" for p in (proj_paths or []))
    return paths


def parse_skill_md(content: str, directory_name: str) -> tuple[str, str]:
    """解析 SKILL.md 的 YAML frontmatter。

    Args:
        content: SKILL.md 的完整内容
        directory_name: 目录名（用作默认 name）

    Returns:
        (name, description) 元组

    Raises:
        ValueError: 如果格式无效或缺少必需字段
    """
    # 分离 YAML frontmatter 和 markdown 正文
    match = re.match(r'^---\n(.*?)\n---\n(.*)$', content, re.DOTALL)
    if not match:
        raise ValueError("无效的 SKILL.md 格式：缺少 YAML frontmatter")

    frontmatter_yaml = match.group(1)

    # 解析 YAML
    try:
        metadata = yaml.safe_load(frontmatter_yaml)
    except yaml.YAMLError as e:
        raise ValueError(f"YAML 解析失败：{e}")

    if metadata is None:
        metadata = {}

    # 验证必需字段
    if "description" not in metadata:
        raise ValueError("SKILL.md 缺少必需字段：description")

    name = metadata.get("name", directory_name)
    description = metadata["description"]

    return name, description


async def _build_directory_tree(
    pool: JuiceFSWorkerPool,
    meta_url: str,
    safe_path: str,
    root_name: str,
) -> str:
    """使用 LISTTREE 构建目录树字符串，类似 Linux tree 命令格式。

    使用 JuiceFS summary() 一次获取完整目录树，避免多次递归 IPC 调用。

    Args:
        pool: JuiceFS worker pool
        meta_url: JuiceFS meta URL
        safe_path: 安全路径
        root_name: 根目录名称

    Returns:
        目录树字符串，格式如：
        my-skill/
        ├── SKILL.md
        ├── template.md
        ├── examples/
        │   └── sample.md
        └── scripts/
            └── validate.sh
    """
    try:
        result = await pool.call(
            meta_url, Operation.LISTTREE, safe_path,
            254,    # depth: 递归深度，skill 目录通常 2-3 层
            100000,  # entries: 每层最大条目数
        )
    except Exception:
        return f"{root_name}/\n"

    summary = result.summary

    def build_tree_from_summary(root: SummaryEntry) -> list[str]:
        """将 SummaryEntry 树转为视觉树行（迭代实现）。"""
        lines = []
        # 栈元素: (children列表, 当前索引, prefix)
        # 使用逆序压栈保证正序弹出
        children = root.Children or []
        children.sort(key=lambda c: (c.Type != "directory", c.Path))
        stack: list[tuple[list[SummaryEntry], int, str]] = [(children, 0, "")]

        while stack:
            children, idx, prefix = stack[-1]
            total = len(children)

            if idx >= total:
                stack.pop()
                continue

            # 推进索引
            stack[-1] = (children, idx + 1, prefix)

            child = children[idx]
            is_last = (idx == total - 1)
            connector = "└── " if is_last else "├── "
            new_prefix = prefix + ("    " if is_last else "│   ")

            # 从 Path 提取文件/目录名
            name = child.Path.rstrip("/").rsplit("/", 1)[-1]

            if child.Type == "directory":
                lines.append(f"{prefix}{connector}{name}/")
                if child.Children:
                    sub = child.Children
                    sub.sort(key=lambda c: (c.Type != "directory", c.Path))
                    stack.append((sub, 0, new_prefix))
            else:
                lines.append(f"{prefix}{connector}{name}")

        return lines

    root_line = f"{root_name}/"

    children = summary.Children
    if children:
        tree_lines = build_tree_from_summary(summary)
        return root_line + "\n" + "\n".join(tree_lines)
    else:
        return root_line


async def _check_exists(
    pool: JuiceFSWorkerPool,
    meta_url: str,
    pvc_name: str,
    path: str,
    expect_dir: bool = False
) -> bool:
    """检查路径是否存在。

    Args:
        pool: JuiceFS worker pool
        meta_url: JuiceFS meta URL
        pvc_name: PVC 名称
        path: 要检查的路径
        expect_dir: 是否期望是目录

    Returns:
        是否存在且符合预期类型
    """
    try:
        safe_path = validate_and_build_path(path, pvc_name)
    except ValueError:
        return False

    try:
        stat_result = await pool.call(meta_url, Operation.STAT, safe_path)
        if expect_dir:
            return stat.S_ISDIR(stat_result.stat_info.st_mode)
        else:
            return stat.S_ISREG(stat_result.stat_info.st_mode)
    except Exception:
        return False


async def _load_skill_by_dir(
    pool: JuiceFSWorkerPool,
    meta_url: str,
    pvc_name: str,
    skill_dir: str,
) -> SkillDefinition | None:
    """按已知目录路径加载 skill 定义（纯加载，无搜索回退）。

    Args:
        pool: JuiceFS worker pool
        meta_url: JuiceFS meta URL
        pvc_name: PVC 名称
        skill_dir: 技能目录相对路径（如 "sys/skills/my-skill"）

    Returns:
        SkillDefinition 或 None
    """
    safe_path = validate_and_build_path(skill_dir, pvc_name)
    dir_name = PurePosixPath(skill_dir).name

    # 读取 SKILL.md
    skill_md_path = str(PurePosixPath(skill_dir) / SKILL_MD_FILENAME)
    try:
        skill_md_safe_path = validate_and_build_path(skill_md_path, pvc_name)
        read_result = await pool.call(meta_url, Operation.READ, skill_md_safe_path)
        skill_md_content = read_result.content.decode("utf-8")
    except Exception:
        return None

    # 解析 frontmatter
    try:
        name, description = parse_skill_md(skill_md_content, dir_name)
    except ValueError:
        return None

    # 构建目录树
    directory_tree = await _build_directory_tree(
        pool, meta_url, safe_path, dir_name
    )

    # 检查可选资源
    has_template = await _check_exists(pool, meta_url, pvc_name, str(PurePosixPath(skill_dir) / "template.md"), expect_dir=False)
    has_examples = await _check_exists(pool, meta_url, pvc_name, str(PurePosixPath(skill_dir) / "examples"), expect_dir=True)
    has_scripts = await _check_exists(pool, meta_url, pvc_name, str(PurePosixPath(skill_dir) / "scripts"), expect_dir=True)

    return SkillDefinition(
        name=name,
        description=description,
        directory_path=skill_dir,
        skill_md_content=skill_md_content,
        directory_tree=directory_tree,
        has_template=has_template,
        has_examples=has_examples,
        has_scripts=has_scripts,
    )


async def load_skill_definition(
    user_id: UUID,
    skill_name: str,
    *,
    role: UserToolCallingPermissionRole | None = None,
    proj_paths: list[PurePosixPath] | None = None,
) -> SkillDefinition | None:
    """加载单个 skill 定义。

    先尝试 skill_name 作为直接路径，失败后回退搜索显示名。
    多路径搜索时，同名技能会触发 SkillConflictError。

    Args:
        user_id: 用户 ID
        skill_name: 技能目录名、相对路径或显示名
        role: 用户角色，None 表示兼容模式
        proj_paths: 项目路径列表

    Returns:
        SkillDefinition 或 None（如果未找到）

    Raises:
        ValueError: 配置无效
        SkillConflictError: 多路径同名冲突
    """
    search_paths = _build_search_paths(role, proj_paths)

    pool = get_worker_pool()
    meta_url = get_meta_url(str(user_id))
    pvc_name = get_pvc_name(str(user_id))

    found: list[SkillDefinition] = []

    for search_root in search_paths:
        skill_dir = str(search_root / skill_name)

        # 1. 尝试直接路径
        try:
            safe_path = validate_and_build_path(skill_dir, pvc_name)
            stat_result = await pool.call(meta_url, Operation.STAT, safe_path)
            if stat.S_ISDIR(stat_result.stat_info.st_mode):
                result = await _load_skill_by_dir(pool, meta_url, pvc_name, skill_dir)
                if result is not None:
                    found.append(result)
                    continue
        except (ValueError, Exception):
            pass

        # 2. 回退：在该搜索路径下按显示名搜索
        result = await _find_skill_by_display_name_in_dir(
            user_id, skill_name, search_root,
        )
        if result is not None:
            found.append(result)

    if len(found) > 1:
        raise SkillConflictError(
            f"技能 '{skill_name}' 在系统路径和项目路径中同时存在，存在冲突"
        )

    return found[0] if found else None


async def _find_skill_by_display_name_in_dir(
    user_id: UUID,
    display_name: str,
    search_root: PurePosixPath,
) -> SkillDefinition | None:
    """在指定搜索路径下通过显示名搜索 skill。

    Args:
        user_id: 用户 ID
        display_name: 技能显示名
        search_root: 搜索根目录（如 sys/skills 或 pub/<proj>/skills）

    Returns:
        SkillDefinition 或 None
    """
    skill_infos = await _load_skill_infos_from_dir(user_id, search_root)

    for info in skill_infos.values():
        if info.name == display_name:
            pool = get_worker_pool()
            meta_url = get_meta_url(str(user_id))
            pvc_name = get_pvc_name(str(user_id))
            return await _load_skill_by_dir(pool, meta_url, pvc_name, info.path)

    return None


def _collect_skill_dirs(summary: SummaryEntry, root_dir: PurePosixPath) -> list[str]:
    """从 SummaryEntry 树中收集所有包含 SKILL.md 的目录相对路径。

    Args:
        summary: LISTTREE 返回的目录树根节点（路径已标准化为相对路径）
        root_dir: 根目录（如 PurePosixPath("sys/skills")）

    Returns:
        相对路径列表（如 ["sys/skills/my-skill", "sys/skills/coding/python-skill"]）
    """
    skill_dirs = []
    stack = list(summary.Children or [])
    while stack:
        current = stack.pop()
        if current.Type == "regular" and current.Path.endswith("/SKILL.md"):
            parent_path = current.Path[: -len("/SKILL.md")]
            skill_dirs.append(str(root_dir / parent_path))
        if current.Children:
            stack.extend(current.Children)
    return skill_dirs


async def load_all_skill_infos(
    user_id: UUID,
    *,
    role: UserToolCallingPermissionRole | None = None,
    proj_paths: list[PurePosixPath] | None = None,
) -> dict[str, SkillInfo]:
    """加载所有可用 skill 的简要信息。

    根据 role/proj_paths 扫描对应的技能目录树。

    Args:
        user_id: 用户 ID
        role: 用户角色，None 表示兼容模式（仅扫描 sys/skills）
        proj_paths: 项目路径列表

    Returns:
        技能名称到 SkillInfo 的映射

    Raises:
        ValueError: 配置无效
    """
    search_paths = _build_search_paths(role, proj_paths)

    skills: dict[str, SkillInfo] = {}
    for search_root in search_paths:
        dir_skills = await _load_skill_infos_from_dir(user_id, search_root)
        skills.update(dir_skills)

    return skills


async def _load_skill_infos_from_dir(
    user_id: UUID,
    search_root: PurePosixPath,
) -> dict[str, SkillInfo]:
    """从单个目录扫描技能简要信息。"""
    pool = get_worker_pool()
    meta_url = get_meta_url(str(user_id))
    pvc_name = get_pvc_name(str(user_id))

    skills: dict[str, SkillInfo] = {}

    try:
        safe_path = validate_and_build_path(str(search_root), pvc_name)
    except ValueError:
        return skills

    try:
        result = await pool.call(
            meta_url, Operation.LISTTREE, safe_path,
            254,   # depth: 最大递归深度
            1000,  # entries: 每层最大条目数
        )
    except Exception:
        return skills

    skill_dirs = _collect_skill_dirs(result.summary, search_root)

    for skill_dir in skill_dirs:
        dir_name = PurePosixPath(skill_dir).name

        try:
            skill_md_path = str(PurePosixPath(skill_dir) / SKILL_MD_FILENAME)
            skill_md_safe_path = validate_and_build_path(skill_md_path, pvc_name)
            read_result = await pool.call(meta_url, Operation.READ, skill_md_safe_path)
            content = read_result.content.decode("utf-8")
            name, description = parse_skill_md(content, dir_name)

            skills[name] = SkillInfo(
                name=name,
                description=description,
                path=skill_dir
            )
        except Exception:
            continue

    return skills