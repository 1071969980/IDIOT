"""JuiceFS 客户端工作进程池数据模型

使用 Pydantic 定义操作的输入输出规范。
"""

from typing import Any, Optional, Union
from pydantic import BaseModel, Field
from dataclasses import dataclass

from api.juiceFS.client_worker.constants import Operation


# ============================================================
# 操作输入模型
# ============================================================

class OperationInput(BaseModel):
    """操作输入基类"""
    pass


class ReadInput(OperationInput):
    """读取文件"""
    path: str


class WriteInput(OperationInput):
    """写入文件"""
    path: str
    data: bytes


class ExistsInput(OperationInput):
    """检查路径是否存在"""
    path: str


class ListdirInput(OperationInput):
    """列出目录内容"""
    path: str
    detail: bool = False


class MkdirInput(OperationInput):
    """创建目录"""
    path: str
    mode: int = Field(default=0o777, description="目录权限")


class MakedirsInput(OperationInput):
    """递归创建目录"""
    path: str
    mode: int = Field(default=0o777, description="目录权限")
    exist_ok: bool = Field(default=False, description="目录已存在时是否忽略")


class RemoveInput(OperationInput):
    """删除文件"""
    path: str


class RmdirInput(OperationInput):
    """删除空目录"""
    path: str


class RmrInput(OperationInput):
    """递归删除目录"""
    path: str


class CloneInput(OperationInput):
    """克隆文件或目录"""
    src: str
    dst: str
    preserve: bool = Field(default=False, description="是否保留文件属性")


class RenameInput(OperationInput):
    """重命名/移动"""
    old: str
    new: str


class StatInput(OperationInput):
    """获取文件状态"""
    path: str


class TruncateInput(OperationInput):
    """截断文件"""
    path: str
    size: int = Field(..., ge=0, description="截断后的文件大小")


class ChmodInput(OperationInput):
    """修改权限"""
    path: str
    mode: int


class GetxattrInput(OperationInput):
    """获取扩展属性"""
    path: str
    name: str


class SetxattrInput(OperationInput):
    """设置扩展属性"""
    path: str
    name: str
    value: bytes
    flags: int = Field(default=0, description="0=创建或替换, 1=仅创建, 2=仅替换")


class ListxattrInput(OperationInput):
    """列出扩展属性"""
    path: str


class RemovexattrInput(OperationInput):
    """删除扩展属性"""
    path: str
    name: str


# ============================================================
# 操作输出模型
# ============================================================

class OperationOutput(BaseModel):
    """操作输出基类"""
    pass


class StatResult(BaseModel):
    """文件状态信息

    对应 os.stat_result 的字段。
    """
    st_mode: int = Field(description="文件权限模式")
    st_ino: int = Field(description="inode 号")
    st_dev: int = Field(description="设备号")
    st_nlink: int = Field(description="硬链接数")
    st_uid: int = Field(description="用户 ID")
    st_gid: int = Field(description="组 ID")
    st_size: int = Field(description="文件大小（字节）")
    st_atime: float = Field(description="最后访问时间（时间戳）")
    st_mtime: float = Field(description="最后修改时间（时间戳）")
    st_ctime: float = Field(description="创建时间（时间戳）")


class ListdirEntry(BaseModel):
    """目录条目（detail=True 时返回）"""
    name: str
    st_mode: int
    st_ino: int
    st_dev: int
    st_nlink: int
    st_uid: int
    st_gid: int
    st_size: int
    st_atime: float
    st_mtime: float
    st_ctime: float


class ReadOutput(OperationOutput):
    """读取文件输出"""
    content: bytes


class WriteOutput(OperationOutput):
    """写入文件输出"""
    bytes_written: int


class ExistsOutput(OperationOutput):
    """检查存在输出"""
    exists: bool


class ListdirOutput(OperationOutput):
    """列出目录输出

    entries 元素类型：
    - str: 文件名（detail=False）
    - ListdirEntry: 文件名和状态信息（detail=True）
    """
    entries: list[Union[str, ListdirEntry]]


class MkdirOutput(OperationOutput):
    """创建目录输出"""
    success: bool


class MakedirsOutput(OperationOutput):
    """递归创建目录输出"""
    success: bool


class RemoveOutput(OperationOutput):
    """删除文件输出"""
    success: bool


class RmdirOutput(OperationOutput):
    """删除空目录输出"""
    success: bool


class RmrOutput(OperationOutput):
    """递归删除目录输出"""
    success: bool


class CloneOutput(OperationOutput):
    """克隆文件或目录输出"""
    success: bool


class RenameOutput(OperationOutput):
    """重命名输出"""
    success: bool


class StatOutput(OperationOutput):
    """获取状态输出"""
    stat_info: StatResult


class TruncateOutput(OperationOutput):
    """截断文件输出"""
    success: bool


class ChmodOutput(OperationOutput):
    """修改权限输出"""
    success: bool


class GetxattrOutput(OperationOutput):
    """获取扩展属性输出"""
    value: bytes


class SetxattrOutput(OperationOutput):
    """设置扩展属性输出"""
    success: bool


class ListxattrOutput(OperationOutput):
    """列出扩展属性输出"""
    names: list[str]


class RemovexattrOutput(OperationOutput):
    """删除扩展属性输出"""
    success: bool


# ============================================================
# 批量操作模型
# ============================================================

class BatchOperationItem(BaseModel):
    """批量操作中的单个操作项"""
    operation: str = Field(description="操作名称")
    args: list[Any] = Field(default_factory=list, description="操作参数")


class BatchInput(OperationInput):
    """批量操作输入"""
    operations: list[BatchOperationItem] = Field(description="操作列表")
    stop_on_error: bool = Field(default=False, description="遇到错误时是否停止")


class BatchResultItem(BaseModel):
    """批量操作中的单个结果项"""
    operation: str = Field(description="操作名称")
    success: bool = Field(description="是否成功")
    data: Optional[dict[str, Any]] = Field(default=None, description="操作结果数据")
    error: Optional[str] = Field(default=None, description="错误信息")


class BatchOutput(OperationOutput):
    """批量操作输出"""
    results: list[BatchResultItem] = Field(description="每个操作的结果")
    total: int = Field(description="总操作数")
    succeeded: int = Field(description="成功数")
    failed: int = Field(description="失败数")


# ============================================================
# 操作注册表
# ============================================================

# 操作枚举 -> (输入模型类, 输出模型类)
OPERATION_REGISTRY: dict[Operation, tuple[type[OperationInput], type[OperationOutput]]] = {
    Operation.READ: (ReadInput, ReadOutput),
    Operation.WRITE: (WriteInput, WriteOutput),
    Operation.EXISTS: (ExistsInput, ExistsOutput),
    Operation.LISTDIR: (ListdirInput, ListdirOutput),
    Operation.MKDIR: (MkdirInput, MkdirOutput),
    Operation.MKDIRS: (MakedirsInput, MakedirsOutput),
    Operation.REMOVE: (RemoveInput, RemoveOutput),
    Operation.RMDIR: (RmdirInput, RmdirOutput),
    Operation.RMR: (RmrInput, RmrOutput),
    Operation.CLONE: (CloneInput, CloneOutput),
    Operation.RENAME: (RenameInput, RenameOutput),
    Operation.STAT: (StatInput, StatOutput),
    Operation.TRUNCATE: (TruncateInput, TruncateOutput),
    Operation.CHMOD: (ChmodInput, ChmodOutput),
    Operation.GETXATTR: (GetxattrInput, GetxattrOutput),
    Operation.SETXATTR: (SetxattrInput, SetxattrOutput),
    Operation.LISTXATTR: (ListxattrInput, ListxattrOutput),
    Operation.REMOVEXATTR: (RemovexattrInput, RemovexattrOutput),
    Operation.BATCH: (BatchInput, BatchOutput),
}


def get_input_model(operation: Operation) -> type[OperationInput]:
    """获取操作的输入模型类"""
    if operation not in OPERATION_REGISTRY:
        raise ValueError(f"Unknown operation: {operation}")
    return OPERATION_REGISTRY[operation][0]


def get_output_model(operation: Operation) -> type[OperationOutput]:
    """获取操作的输出模型类"""
    if operation not in OPERATION_REGISTRY:
        raise ValueError(f"Unknown operation: {operation}")
    return OPERATION_REGISTRY[operation][1]


# ============================================================
# 内部任务/结果数据结构
# ============================================================

@dataclass
class Task:
    """任务定义（内部使用，跨进程传递）

    注意：operation 存储为字符串值（非枚举），
    因为枚举在跨进程序列化时可能有问题。
    """
    task_id: str  # UUID v7 字符串
    meta_url: str
    operation: str  # Operation 枚举的值
    args: tuple


@dataclass
class Result:
    """结果定义（内部使用，跨进程传递）"""
    task_id: str  # UUID v7 字符串
    status: str  # "ok" or "error"
    data: Any
    error_msg: Optional[str] = None