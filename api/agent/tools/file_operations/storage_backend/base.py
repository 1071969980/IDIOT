"""
文件操作存储后端抽象基类
定义所有存储后端必须实现的接口
"""

from abc import ABC, abstractmethod
from typing import Literal
from uuid import UUID
from pydantic import BaseModel


class DirectoryItem(BaseModel):
    """
    目录项模型

    代表目录列表中的单个项目，包含名称和类型信息。
    """
    name: str
    type: Literal["file", "directory"]

    class Config:
        frozen = True  # 防止意外修改


class OperationResult(BaseModel):
    """
    操作结果模型

    代表文件/文件夹操作的结果，包含操作类型和详细信息。
    """
    success: bool
    item_type: Literal["file", "directory"]  # 操作的是文件还是目录
    source_path: str | None = None
    destination_path: str | None = None
    message: str | None = None

    class Config:
        frozen = True


class FileOperationsStorageBackend(ABC):
    """
    文件操作存储后端抽象基类

    所有文件操作存储后端都必须继承此类并实现所有抽象方法。
    提供文件读取、编辑、写入的核心功能。
    """

    def __init__(self, session_id: UUID, user_id: UUID | None = None):
        """
        初始化存储后端

        Args:
            session_id: 会话 ID，用于隔离不同会话的文件数据
            user_id: 用户 ID（可选，某些后端如 JuiceFSSdkBackend 需要）
        """
        self.session_id = session_id
        self.user_id = user_id

    # ========== 读取操作 ==========

    @abstractmethod
    async def read_file(
        self,
        file_path: str,
        offset: int | None = None,
        limit: int | None = None
    ) -> tuple[str, int, int]:
        """
        读取文件内容

        Args:
            file_path: 文件路径
            offset: 起始行偏移（从0开始），None 表示从头开始
            limit: 最大读取行数，None 表示读到文件末尾

        Returns:
            (content, first_line_number, total_lines)
            - content: 文件内容字符串
            - first_line_number: 第一行的行号（从1开始，考虑 offset）
            - total_lines: 文件总行数

        Raises:
            FileNotFoundError: 文件不存在
            PermissionError: 无权限访问
            ValueError: 路径无效或包含隐藏组件
        """
        pass

    # ========== 编辑操作 ==========

    @abstractmethod
    async def edit_file(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False
    ) -> tuple[bool, int, str]:
        """
        编辑文件内容，替换指定字符串

        Args:
            file_path: 文件路径
            old_string: 要替换的字符串
            new_string: 替换后的字符串
            replace_all: 是否替换所有匹配项

        Returns:
            (success, replace_count, updated_content)
            - success: 是否成功
            - replace_count: 替换次数
            - updated_content: 更新后的内容

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: old_string 不存在或重复出现且 replace_all=False
            PermissionError: 无权限编辑
        """
        pass

    # ========== 写入操作 ==========

    @abstractmethod
    async def write_file(
        self,
        file_path: str,
        content: str,
        mode: Literal["create", "overwrite"] = "create"
    ) -> bool:
        """
        写入文件内容

        Args:
            file_path: 文件路径
            content: 文件内容
            mode: 写入模式（"create" 或 "overwrite"）

        Returns:
            True 如果成功

        Raises:
            FileExistsError: 文件已存在且 mode="create"
            PermissionError: 无权限写入
            ValueError: 路径无效或参数无效
        """
        pass

    # ========== 辅助方法 ==========

    @abstractmethod
    async def file_exists(self, file_path: str) -> bool:
        """检查文件是否存在"""
        pass

    @abstractmethod
    async def get_item_type(self, path: str) -> Literal["file", "directory"] | None:
        """
        获取路径对应的项类型

        Args:
            path: 路径

        Returns:
            "file", "directory" 或 None（不存在）
        """
        pass

    # ========== 删除操作 ==========

    @abstractmethod
    async def delete_item(self, path: str) -> OperationResult:
        """
        删除文件或目录

        Args:
            path: 要删除的路径（文件或目录）

        Returns:
            OperationResult: 包含操作结果和项类型信息
        """
        pass

    # ========== 移动操作 ==========

    @abstractmethod
    async def move_item(
        self,
        source_path: str,
        destination_path: str
    ) -> OperationResult:
        """
        移动/重命名文件或目录

        Args:
            source_path: 源路径（文件或目录）
            destination_path: 目标路径

        Returns:
            OperationResult: 包含操作结果和项类型信息

        Raises:
            FileNotFoundError: 源路径不存在
            FileExistsError: 目标路径已存在
            ValueError: 路径无效
            PermissionError: 无权限
        """
        pass

    # ========== 复制操作 ==========

    @abstractmethod
    async def copy_item(
        self,
        source_path: str,
        destination_path: str
    ) -> OperationResult:
        """
        复制文件或目录

        Args:
            source_path: 源路径（文件或目录）
            destination_path: 目标路径

        Returns:
            OperationResult: 包含操作结果和项类型信息

        Raises:
            FileNotFoundError: 源路径不存在
            FileExistsError: 目标路径已存在
            ValueError: 路径无效
            PermissionError: 无权限
        """
        pass

    @abstractmethod
    async def list_directory(
        self,
        directory_path: str = "."
    ) -> list[DirectoryItem]:
        """列出目录内容（可选实现）

        Returns:
            list[DirectoryItem]: 包含文件/目录名称和类型的列表
        """
        pass
