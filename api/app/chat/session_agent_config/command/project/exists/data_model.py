from pydantic import BaseModel, Field


class ProjectExistsInput(BaseModel):
    project_path: str = Field(description="项目相对路径")
    branch_name: str | None = Field(
        default=None,
        description="分支名称，用于读取 overlay。为空则只读取基础配置",
    )


class ProjectExistsOutput(BaseModel):
    exists: bool = Field(description="项目是否在会话中启用")
    project_path: str = Field(description="项目路径")
