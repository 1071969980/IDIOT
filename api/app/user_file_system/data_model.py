"""用户文件系统 API 数据模型"""

from typing import Optional
from pydantic import BaseModel, Field


class FileInfo(BaseModel):
    """文件/目录信息"""

    name: str = Field(..., description="文件名")
    path: str = Field(..., description="完整路径")
    is_dir: bool = Field(..., description="是否为目录")
    size: int = Field(default=0, description="文件大小（字节）")
    st_mode: int = Field(default=0, description="文件权限模式")
    st_mtime: float = Field(default=0.0, description="最后修改时间（时间戳）")


# ============================================================
# 列出目录
# ============================================================


class ListDirRequest(BaseModel):
    """列出目录请求"""

    path: str = Field(..., description="目录路径")


class ListDirResponse(BaseModel):
    """列出目录响应"""

    entries: list[FileInfo] = Field(default_factory=list, description="目录条目列表")


# ============================================================
# 创建目录
# ============================================================


class CreateDirRequest(BaseModel):
    """创建目录请求"""

    path: str = Field(..., description="目录路径")
    exist_ok: bool = Field(default=False, description="目录已存在时是否忽略")


class CreateDirResponse(BaseModel):
    """创建目录响应"""

    success: bool = Field(..., description="是否成功")
    path: str = Field(..., description="创建的目录路径")


# ============================================================
# 写入文件
# ============================================================


class WriteFileRequest(BaseModel):
    """写入文件请求"""

    path: str = Field(..., description="文件路径")
    content: bytes = Field(..., description="文件内容")


class WriteFileResponse(BaseModel):
    """写入文件响应"""

    success: bool = Field(..., description="是否成功")
    bytes_written: int = Field(..., description="写入的字节数")
    path: str = Field(..., description="文件路径")


# ============================================================
# 读取文件
# ============================================================


class ReadFileRequest(BaseModel):
    """读取文件请求"""

    path: str = Field(..., description="文件路径")


class ReadFileResponse(BaseModel):
    """读取文件响应"""

    content: bytes = Field(..., description="文件内容")
    path: str = Field(..., description="文件路径")


# ============================================================
# 移动/重命名
# ============================================================


class MoveRequest(BaseModel):
    """移动/重命名请求"""

    source: str = Field(..., description="源路径")
    destination: str = Field(..., description="目标路径")


class MoveResponse(BaseModel):
    """移动/重命名响应"""

    success: bool = Field(..., description="是否成功")
    source: str = Field(..., description="源路径")
    destination: str = Field(..., description="目标路径")


# ============================================================
# 复制
# ============================================================


class CopyRequest(BaseModel):
    """复制请求"""

    source: str = Field(..., description="源路径")
    destination: str = Field(..., description="目标路径")


class CopyResponse(BaseModel):
    """复制响应"""

    success: bool = Field(..., description="是否成功")
    source: str = Field(..., description="源路径")
    destination: str = Field(..., description="目标路径")


# ============================================================
# 删除
# ============================================================


class DeleteRequest(BaseModel):
    """删除请求"""

    path: str = Field(..., description="要删除的路径")
    recursive: bool = Field(default=False, description="是否递归删除目录")


class DeleteResponse(BaseModel):
    """删除响应"""

    success: bool = Field(..., description="是否成功")
    path: str = Field(..., description="删除的路径")


# ============================================================
# 检查存在
# ============================================================


class ExistsRequest(BaseModel):
    """检查存在请求"""

    path: str = Field(..., description="路径")


class ExistsResponse(BaseModel):
    """检查存在响应"""

    exists: bool = Field(..., description="是否存在")
    is_dir: Optional[bool] = Field(default=None, description="是否为目录（仅存在时有效）")
    path: str = Field(..., description="检查的路径")


# ============================================================
# 获取状态
# ============================================================


class StatRequest(BaseModel):
    """获取状态请求"""

    path: str = Field(..., description="路径")


class StatResponse(BaseModel):
    """获取状态响应"""

    name: str = Field(..., description="文件名")
    path: str = Field(..., description="完整路径")
    is_dir: bool = Field(..., description="是否为目录")
    size: int = Field(..., description="文件大小（字节）")
    st_mode: int = Field(..., description="文件权限模式")
    st_ino: int = Field(..., description="inode 号")
    st_nlink: int = Field(..., description="硬链接数")
    st_mtime: float = Field(..., description="最后修改时间（时间戳）")
    st_atime: float = Field(..., description="最后访问时间（时间戳）")
    st_ctime: float = Field(..., description="创建时间（时间戳）")


# ============================================================
# 上传文件
# ============================================================


class UploadResponse(BaseModel):
    """上传文件响应"""

    success: bool = Field(..., description="是否成功")
    path: str = Field(..., description="文件路径")
    bytes_written: int = Field(..., description="写入的字节数")