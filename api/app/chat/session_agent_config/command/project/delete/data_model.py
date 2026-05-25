from pydantic import BaseModel, Field


class DeleteProjectInput(BaseModel):
    project_path: str = Field(description="项目相对路径")
    branch_name: str = Field(description="分支名称，用于写入 overlay")


class DeleteProjectOutput(BaseModel):
    success: bool = Field(description="是否成功")
    project_path: str = Field(description="项目路径")
