"""memory_write 工具的消息模板"""

# ---------------------------------------------------------------------------
# 记忆类型定义
# ---------------------------------------------------------------------------

MEMORY_TYPE_DEFINITIONS: list[dict[str, str]] = [
    {
        "type": "user",
        "purpose": "用户角色、偏好、知识水平",
        "trigger": "了解到用户的个人特征、习惯或专业背景时更新",
    },
    {
        "type": "feedback",
        "purpose": "用户对工作方式的指导",
        "trigger": "用户纠正或确认你的做法时更新",
    },
    {
        "type": "project",
        "purpose": "项目动态、目标、外部影响因素",
        "trigger": "了解到项目文件/git无法推断的项目信息时更新",
    },
    {
        "type": "reference",
        "purpose": "外部系统的指引",
        "trigger": "了解到外部资源的位置、访问方法和用途时更新",
    },
    {
        "type": "knowledge",
        "purpose": "无法明确与项目紧密相关的信息",
        "trigger": "用户披露令人意外的信息时更新",
    },
]

# ---------------------------------------------------------------------------
# 目录作用域：各目录的设计目的
# ---------------------------------------------------------------------------

DIRECTORY_SCOPE_MAP: dict[str, dict[str, str]] = {
    "global": {
        "label": "全局记忆",
        "description": "跨项目通用的用户偏好和知识。存储在 `/dist_fs/sys/memory/global`。",
    },
    "projects": {
        "label": "项目记忆",
        "description": "特定项目的约定、架构决策和动态。每个项目拥有独立子目录，存储在 `/dist_fs/sys/memory/projects/<project_path>`。",
    },
    "external_facing": {
        "label": "外部交互记忆",
        "description": "除用户（拥有者）以外，其他实体与系统交互产生的记忆存储。每个外部实体拥有独立子目录，存储在 `/dist_fs/sys/memory/external_facing/<entity_identifier>`。",
    },
}


# ---------------------------------------------------------------------------
# 提示词构建
# ---------------------------------------------------------------------------


def _build_type_table() -> str:
    """渲染记忆类型定义表格。"""
    header = "| 类型 | 用途 | 更新触发条件 |\n|------|------|-------------|"
    rows = [
        f"| {d['type']} | {d['purpose']} | {d['trigger']} |"
        for d in MEMORY_TYPE_DEFINITIONS
    ]
    return header + "\n" + "\n".join(rows)


def _build_scope_descriptions() -> str:
    """渲染静态的目录作用域描述。"""
    parts: list[str] = []
    for scope_info in DIRECTORY_SCOPE_MAP.values():
        parts.append(f"- **{scope_info['label']}**：{scope_info['description']}")
    return "\n".join(parts)


def build_write_work_requirements() -> str:
    """构建记忆写入工作要求。"""
    type_table = _build_type_table()
    scope_desc = _build_scope_descriptions()
    return (
        "## 记忆写入任务\n\n"
        "你是记忆维护 Agent。你的任务是根据本次交互的内容，判断是否需要新增、修改或删除记忆文件。\n\n"
        "## 记忆目录\n\n"
        f"{scope_desc}\n\n"
        "## 记忆类型定义\n\n"
        f"{type_table}\n\n"
        "## 记忆文件格式\n\n"
        "每个记忆文件为 Markdown 格式，包含 YAML Frontmatter 和正文：\n\n"
        "```markdown\n"
        "---\n"
        "name: 简明标题\n"
        "description: 一句话描述该记忆的核心内容\n"
        "type: user  # user | feedback | project | reference | knowledge\n"
        "---\n\n"
        "正文内容，简洁准确地记录关键信息。\n"
        "正文应保持简洁，通常在 200 字以内，聚焦事实和可操作的信息。\n"
        "```\n\n"
        "## 记忆文件示例\n\n"
        "```markdown\n"
        "---\n"
        "name: 用户是高级后端工程师\n"
        "description: 用户是一名有10年Go经验的高级工程师，第一次接触React前端\n"
        "type: user\n"
        "---\n\n"
        "用户是一名高级后端工程师，深耕Go语言十年。\n"
        "目前第一次接触项目的React前端部分。\n\n"
        "解释前端概念时，应该用后端类比来帮助理解。\n"
        "比如把组件生命周期类比为请求处理中间件链。\n"
        "```\n\n"
        "## MEMORY.md 索引格式\n\n"
        "MEMORY.md 是记忆目录的索引文件，使用链接列表格式：\n\n"
        "```markdown\n"
        "- [用户是高级后端工程师](user_role.md) — Go专家，React新手，用后端类比解释前端\n"
        "- [测试必须用真实数据库](feedback_testing.md) — 不要 mock 数据库，曾因此出过生产事故\n"
        "```\n\n"
        "每条记录包含：文件链接 + ` — ` + 一句话摘要。\n\n"
        "## 工作流程\n\n"
        "1. 阅读下方提供的各目录 MEMORY.md 索引，了解已有记忆条目\n"
        "2. 根据本次交互内容，判断是否需要新增、修改或删除记忆\n"
        "3. 使用文件操作工具完成记忆文件的增删改\n"
        "4. 对每个修改过的记忆目录，运行索引重建脚本（见下方）\n\n"
        "## 索引重建与合规检查\n\n"
        "所有记忆文件操作完成后，对每个变更的记忆目录运行：\n\n"
        "```\n"
        "/dist_fs/sys/builtin_scripts/memory_maintainer/rebuild_index.sh /dist_fs/sys/memory/<目录路径>\n"
        "```\n\n"
        "例如：\n"
        "```\n"
        "/dist_fs/sys/builtin_scripts/memory_maintainer/rebuild_index.sh /dist_fs/sys/memory/global\n"
        "```\n\n"
        "脚本会自动：\n"
        "- 扫描目录中的所有 .md 记忆文件\n"
        "- 解析 frontmatter，检查格式合规性\n"
        "- 重新生成 MEMORY.md 索引文件\n\n"
        "脚本会报告格式不符合规范的文件（缺少 frontmatter、type 无效、正文过长等），"
        "但不会自动修改或删除记忆文件。\n\n"
        "如果脚本因意外不存在或运行失败，作为 fallback，"
        "使用 write_file 工具手动更新 MEMORY.md 索引文件，格式为：\n\n"
        "```\n"
        "- [标题](文件名.md) — 一句话摘要\n"
        "```\n\n"
        "## 工作原则\n\n"
        "- 只更新确实需要变更的记忆，不要随意修改已有的正确记忆\n"
        "- 新增记忆时，选择最合适的类型和目录\n"
        "- 保持正文简洁，避免冗余信息\n"
        "- MEMORY.md 索引的摘要应准确反映记忆内容\n"
        "- 完成文件操作后，务必运行索引重建脚本\n"
    )


def build_write_context_msg(memory_indices: list[tuple[str, str]]) -> str:
    """组装记忆写入上下文消息。

    Args:
        memory_indices: 每个元素为 (directory_path, memory_md_content)。
    """
    parts = [build_write_work_requirements()]

    if memory_indices:
        indices_sections: list[str] = []
        for dir_path, content in memory_indices:
            indices_sections.append(f"### 记忆目录: {dir_path}\n{content}")
        parts.append("\n\n".join(indices_sections))

    return "\n\n".join(parts)
