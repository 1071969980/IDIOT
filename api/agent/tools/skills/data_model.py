# api/agent/tools/skills/data_model.py

"""Skill 相关的数据模型。"""

from dataclasses import dataclass

from pydantic import BaseModel, Field

LOADED_SKILLS_KEY_IN_TASK_STORAGE_SNAPSHOT = "loaded_skills"

@dataclass
class SkillDefinition:
    """从 JuiceFS 加载的 Skill 定义。

    Attributes:
        name: 技能显示名（来自 YAML 或目录名）
        description: 技能描述（来自 YAML，必需）
        directory_path: 技能目录路径
        skill_md_content: SKILL.md 完整内容（包含 frontmatter）
        directory_tree: 目录树字符串表示
        has_template: 是否存在 template.md
        has_examples: 是否存在 examples/ 目录
        has_scripts: 是否存在 scripts/ 目录
    """

    name: str
    description: str
    directory_path: str
    skill_md_content: str
    directory_tree: str
    has_template: bool
    has_examples: bool
    has_scripts: bool


class SkillInfo(BaseModel):
    """Skill 简要信息，用于列表和 advisor。"""

    name: str = Field(description="技能显示名")
    description: str = Field(description="技能描述")
    path: str = Field(description="技能目录路径")


class SkillRecommendation(BaseModel):
    """单个 skill 推荐。"""

    skill_name: str = Field(description="技能显示名")
    skill_path: str = Field(description="技能目录路径")
    relevance_reason: str = Field(description="相关性理由")


class SkillAdvisorResult(BaseModel):
    """skill_advisor 的结构化结果。"""

    recommendations: list[SkillRecommendation] = Field(
        default_factory=list,
        description="推荐的技能列表"
    )
    analysis: str = Field(
        default="",
        description="问题分析和技能匹配分析"
    )


class SkillLoadResult(BaseModel):
    """load_skill 的结构化结果。"""

    name: str = Field(description="技能显示名")
    description: str = Field(description="技能描述")
    directory_path: str = Field(description="技能目录路径")
    directory_tree: str = Field(description="目录树字符串")
    skill_md_content: str = Field(description="SKILL.md 完整内容")
    available_resources: dict[str, bool] = Field(
        description="可用资源标记（template, examples, scripts）"
    )