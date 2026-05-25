"""用户项目数据模型"""

from pydantic import BaseModel, Field


# ============================================================
# 创建项目
# ============================================================


class CreateProjectRequest(BaseModel):
    """创建项目请求"""

    project_path: str = Field(..., description="项目相对路径")
    enable_memory: bool = Field(default=True, description="是否开启记忆功能")


class CreateProjectResponse(BaseModel):
    """创建项目响应"""

    success: bool = Field(..., description="是否成功")
    project_path: str = Field(..., description="项目路径")
    memory_enabled: bool = Field(..., description="是否创建了记忆文件夹")


# ============================================================
# 查询项目是否存在
# ============================================================


class ProjectExistsRequest(BaseModel):
    """查询项目是否存在请求"""

    project_path: str = Field(..., description="项目相对路径")


class ProjectExistsResponse(BaseModel):
    """查询项目是否存在响应"""

    exists: bool = Field(..., description="是否存在")
    project_path: str = Field(..., description="项目路径")


# ============================================================
# 删除项目
# ============================================================


class DeleteProjectRequest(BaseModel):
    """删除项目请求"""

    project_path: str = Field(..., description="项目相对路径")


class DeleteProjectResponse(BaseModel):
    """删除项目响应"""

    success: bool = Field(..., description="是否成功")
    project_path: str = Field(..., description="项目路径")


# ============================================================
# 独立创建项目记忆文件夹
# ============================================================


class CreateProjectMemoryRequest(BaseModel):
    """独立创建项目记忆文件夹请求"""

    project_path: str = Field(..., description="项目相对路径")


class CreateProjectMemoryResponse(BaseModel):
    """独立创建项目记忆文件夹响应"""

    success: bool = Field(..., description="是否成功")
    project_path: str = Field(..., description="项目路径")
