# api/agent/tools/skills/definition_loader.py

"""Skill 定义加载器，从 JuiceFS 加载 skill 信息。"""

import re
import stat
from dataclasses import dataclass
from uuid import UUID

import yaml

from api.juiceFS.client_worker import Operation, get_worker_pool
from api.juiceFS.client_worker.models import FileInfo
from api.juiceFS.path_utils import get_meta_url, get_pvc_name, validate_and_build_path
from api.juiceFS.client_worker.pool import JuiceFSWorkerPool

from .data_model import SkillDefinition, SkillInfo


SKILLS_DIR = "sys/skills"
SKILL_MD_FILENAME = "SKILL.md"


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
            1000,  # entries: 每层最大条目数
        )
    except Exception:
        return f"{root_name}/\n"

    summary = result.summary

    def build_tree_from_summary(root) -> list[str]:
        """将 SummaryEntry 树转为视觉树行（迭代实现）。"""
        lines = []
        # 栈元素: (children列表, 当前索引, prefix)
        # 使用逆序压栈保证正序弹出
        children = root.Children or []
        children.sort(key=lambda c: (c.Type != "directory", c.Path))
        stack: list[tuple[list, int, str]] = [(children, 0, "")]

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


async def load_skill_definition(user_id: UUID, skill_name: str) -> SkillDefinition | None:
    """加载单个 skill 定义。

    Args:
        user_id: 用户 ID
        skill_name: 技能目录名或显示名

    Returns:
        SkillDefinition 或 None（如果未找到）
    """
    pool = get_worker_pool()
    meta_url = get_meta_url(str(user_id))
    pvc_name = get_pvc_name(str(user_id))

    # 首先尝试直接使用 skill_name 作为目录名
    skill_dir = f"{SKILLS_DIR}/{skill_name}"

    try:
        safe_path = validate_and_build_path(skill_dir, pvc_name)
    except ValueError:
        return None

    # 检查目录是否存在
    try:
        stat_result = await pool.call(meta_url, Operation.STAT, safe_path)
        if not stat.S_ISDIR(stat_result.stat_info.st_mode):
            # 不是目录，尝试搜索匹配显示名
            return await _find_skill_by_display_name(user_id, skill_name)
    except Exception:
        # 目录不存在，尝试搜索匹配显示名
        return await _find_skill_by_display_name(user_id, skill_name)

    # 读取 SKILL.md
    skill_md_path = f"{skill_dir}/{SKILL_MD_FILENAME}"
    try:
        skill_md_safe_path = validate_and_build_path(skill_md_path, pvc_name)
        read_result = await pool.call(meta_url, Operation.READ, skill_md_safe_path)
        skill_md_content = read_result.content.decode("utf-8")
    except Exception:
        return None  # SKILL.md 是必需的

    # 解析 frontmatter
    try:
        name, description = parse_skill_md(skill_md_content, skill_name)
    except ValueError:
        return None

    # 构建目录树
    directory_tree = await _build_directory_tree(
        pool, meta_url, safe_path, skill_name
    )

    # 检查可选资源
    has_template = await _check_exists(pool, meta_url, pvc_name, f"{skill_dir}/template.md", expect_dir=False)
    has_examples = await _check_exists(pool, meta_url, pvc_name, f"{skill_dir}/examples", expect_dir=True)
    has_scripts = await _check_exists(pool, meta_url, pvc_name, f"{skill_dir}/scripts", expect_dir=True)

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


async def _find_skill_by_display_name(user_id: UUID, display_name: str) -> SkillDefinition | None:
    """通过显示名搜索 skill。

    Args:
        user_id: 用户 ID
        display_name: 技能显示名

    Returns:
        SkillDefinition 或 None
    """
    skill_infos = await load_all_skill_infos(user_id)

    for info in skill_infos.values():
        if info.name == display_name:
            # 找到匹配的，使用目录名重新加载
            dir_name = info.path.split("/")[-1]
            return await load_skill_definition(user_id, dir_name)

    return None


async def load_all_skill_infos(user_id: UUID) -> dict[str, SkillInfo]:
    """加载所有可用 skill 的简要信息。

    Args:
        user_id: 用户 ID

    Returns:
        技能名称到 SkillInfo 的映射
    """
    pool = get_worker_pool()
    meta_url = get_meta_url(str(user_id))
    pvc_name = get_pvc_name(str(user_id))

    skills: dict[str, SkillInfo] = {}

    try:
        safe_path = validate_and_build_path(SKILLS_DIR, pvc_name)
    except ValueError:
        return skills

    # 列出 skills 目录
    try:
        result = await pool.call(meta_url, Operation.LISTDIR, safe_path, True)
    except Exception:
        return skills

    entries = result.entries if hasattr(result, 'entries') else []

    for entry in entries:
        if not isinstance(entry, FileInfo):
            continue
        if not stat.S_ISDIR(entry.st_mode):
            continue  # skills 是目录

        skill_dir_name = entry.name
        skill_dir = f"{SKILLS_DIR}/{skill_dir_name}"

        # 读取并解析 SKILL.md
        try:
            skill_md_path = f"{skill_dir}/{SKILL_MD_FILENAME}"
            skill_md_safe_path = validate_and_build_path(skill_md_path, pvc_name)
            read_result = await pool.call(meta_url, Operation.READ, skill_md_safe_path)
            content = read_result.content.decode("utf-8")
            name, description = parse_skill_md(content, skill_dir_name)

            skills[name] = SkillInfo(
                name=name,
                description=description,
                path=skill_dir
            )
        except Exception:
            continue  # 跳过无效的 skill

    return skills