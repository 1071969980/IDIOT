"""用户文件系统 API 数据模型"""

from pathlib import PurePosixPath
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from api.juiceFS.client_worker.models import FileInfo as BaseFileInfo


# ============================================================
# 受保护的初始目录
# ============================================================

# 受保护的初始目录名称（不含 PVC 前缀）
# 保护机制说明：这些目录由 api.juiceFS.creator.init_dir_juicefs_for_user 创建，
# 在 DeleteRequest、MoveRequest、CopyRequest 的字段验证器中进行保护，
# 阻止删除、移动或复制覆盖这些目录。
PROTECTED_DIR_NAMES = frozenset(["sys", "pub", "priv"])


def validate_not_protected_path(path: str) -> str:
    """验证路径不是受保护的初始目录

    保护规则：
    - 根目录 '/' 受保护
    - '/sys'、'/pub'、'/priv' 三个初始目录本身受保护
    - 子路径（如 '/sys/config.json'）允许操作

    Args:
        path: 用户输入的路径

    Raises:
        ValueError: 路径是受保护的初始目录
    """
    normalized = PurePosixPath(path.strip())

    # 根目录受保护
    if str(normalized) == "." or str(normalized) == "/":
        raise ValueError("根目录受保护，禁止此操作")

    # 获取路径段
    parts = normalized.parts
    if parts and parts[0] == "/":
        # 绝对路径：('/sys',) 或 ('/', 'sys') 取最后一段
        top_dir = parts[-1] if len(parts) == 2 and parts[0] == "/" else None
    elif parts and len(parts) == 1:
        # 相对路径单段：('sys',)
        top_dir = parts[0]
    else:
        # 多段路径，不是顶级目录
        top_dir = None

    # 仅当路径正好是顶级初始目录时受保护
    if top_dir in PROTECTED_DIR_NAMES:
        raise ValueError(f"目录 '{top_dir}' 是系统初始目录，禁止此操作")

    return path


class FileInfo(BaseFileInfo):
    """文件/目录信息

    继承 worker 层 FileInfo，添加 path 和 is_dir 字段用于 API 响应。
    """

    path: str = Field(description="完整路径")
    is_dir: bool = Field(description="是否为目录")


# StatResponse 别名，保持向后兼容
StatResponse = FileInfo


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

    @field_validator("source", "destination")
    @classmethod
    def validate_paths_not_protected(cls, v: str) -> str:
        return validate_not_protected_path(v)


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

    @field_validator("destination")
    @classmethod
    def validate_destination_not_protected(cls, v: str) -> str:
        """验证目标路径不是受保护的初始目录"""
        return validate_not_protected_path(v)


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

    @field_validator("path")
    @classmethod
    def validate_path_not_protected(cls, v: str) -> str:
        return validate_not_protected_path(v)


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


# StatResponse 已在文件顶部定义为 FileInfo 的别名


# ============================================================
# 上传文件
# ============================================================


class UploadResponse(BaseModel):
    """上传文件响应"""

    success: bool = Field(..., description="是否成功")
    path: str = Field(..., description="文件路径")
    bytes_written: int = Field(..., description="写入的字节数")