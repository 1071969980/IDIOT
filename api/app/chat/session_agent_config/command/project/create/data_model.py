from pathlib import PurePosixPath

from pydantic import BaseModel, Field


def build_project_rel_path(project_path: str) -> PurePosixPath:
    """构建项目相对路径"""
    return PurePosixPath("pub") / PurePosixPath(project_path.strip())


def build_memory_rel_path(project_path: str) -> PurePosixPath:
    """构建项目记忆相对路径"""
    return PurePosixPath("sys") / "memory" / "projects" / PurePosixPath(project_path.strip())


class CreateProjectInput(BaseModel):
    project_path: str = Field(description="项目相对路径")
    enable_memory: bool = Field(default=True, description="是否同时启用记忆目录")
    branch_name: str = Field(description="分支名称，用于写入 overlay")


class CreateProjectOutput(BaseModel):
    success: bool = Field(description="是否成功")
    project_path: str = Field(description="项目路径")
    memory_enabled: bool = Field(description="是否启用了记忆目录")
