from pydantic import BaseModel, Field


class ToolStatusUpdate(BaseModel):
    tool_name: str = Field(description="工具名称")
    enabled: bool = Field(description="是否启用")
    explicit: bool | None = Field(
        default=None,
        description="是否显式加载。为空表示不修改此字段"
    )


class UpdateToolsStatusInput(BaseModel):
    tools_status: list[ToolStatusUpdate] = Field(description="要更新的工具状态列表")
    branch_name: str = Field(description="分支名称，用于写入 overlay")


class UpdatedToolStatus(BaseModel):
    tool_name: str
    enabled: bool
    explicit: bool


class UpdateToolsStatusOutput(BaseModel):
    updated_tools: list[UpdatedToolStatus]
