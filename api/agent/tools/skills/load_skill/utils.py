
from api.agent.tools.skills.data_model import SkillDefinition


def _format_skill_info(skill_def: SkillDefinition) -> str:
    """格式化技能信息为可读文本。"""
    lines = [
        f"# 技能: {skill_def.name}",
        f"\n**描述:** {skill_def.description}",
        f"\n**路径:** {skill_def.directory_path}",
        f"\n## 目录结构",
        "```",
        skill_def.directory_tree,
        "```",
        f"\n## SKILL.md 内容",
        "```markdown",
        skill_def.skill_md_content,
        "```",
    ]

    resources = []
    if skill_def.has_template:
        resources.append("template.md")
    if skill_def.has_examples:
        resources.append("examples/")
    if skill_def.has_scripts:
        resources.append("scripts/")

    if resources:
        lines.append(f"\n**可用资源:** {', '.join(resources)}")

    return "\n".join(lines)