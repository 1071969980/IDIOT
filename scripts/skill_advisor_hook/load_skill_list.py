"""从 JuiceFS 读取技能列表并格式化输出，供 skill_advisor 子代理 hook 使用。"""

import re
from pathlib import Path

import yaml

DIST_FS_MOUNT_PATH = "/dist_fs"
SKILLS_DIR = "sys/skills"
SKILL_MD_FILENAME = "SKILL.md"


def parse_skill_md(content: str, directory_name: str) -> tuple[str, str]:
    """解析 SKILL.md 的 YAML frontmatter，返回 (name, description)。"""
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", content, re.DOTALL)
    if not match:
        raise ValueError("缺少 YAML frontmatter")

    metadata = yaml.safe_load(match.group(1))
    if metadata is None:
        metadata = {}

    if "description" not in metadata:
        raise ValueError("缺少必需字段：description")

    name = metadata.get("name", directory_name)
    return name, metadata["description"]


def main() -> None:
    skills_root = Path(DIST_FS_MOUNT_PATH) / SKILLS_DIR

    if not skills_root.is_dir():
        print("当前无可用技能。")
        return

    entries = sorted(skills_root.iterdir())
    skill_lines: list[str] = []

    for entry in entries:
        if not entry.is_dir():
            continue

        skill_md = entry / SKILL_MD_FILENAME
        if not skill_md.is_file():
            continue

        try:
            content = skill_md.read_text(encoding="utf-8")
            name, description = parse_skill_md(content, entry.name)
            skill_lines.append(f"- {name}: {description} (路径: {SKILLS_DIR}/{entry.name})")
        except Exception:
            continue

    if not skill_lines:
        print("当前无可用技能。")
    else:
        print("可用技能列表：")
        for line in skill_lines:
            print(line)


if __name__ == "__main__":
    main()
