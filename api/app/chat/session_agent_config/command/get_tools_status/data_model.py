from pydantic import BaseModel, Field


class GetToolsStatusInput(BaseModel):
    tool_names: list[str] = Field(
        default_factory=list,
        description="要查询的工具名称列表，为空表示获取所有工具"
    )
    branch_name: str | None = Field(
        default=None,
        description="分支名称，用于读取 overlay。为空则只读取基础配置"
    )


class ToolStatus(BaseModel):
    tool_name: str
    enabled: bool
    explicit: bool


class GetToolsStatusOutput(BaseModel):
    tools_status: list[ToolStatus]
