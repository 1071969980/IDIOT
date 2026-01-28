---
文档标题：storage_backend_design
文档描述：文件操作工具的存储后端抽象接口定义和三种存储后端（内存、本地文件、用户空间文件系统）的设计。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [存储后端概述](#存储后端概述)
- [抽象接口定义](#抽象接口定义)
- [MemoryFileBackend 设计](#memoryfilebackend-设计)
- [LocalFileBackend 设计](#localfilebackend-设计)
- [UserSpaceFileBackend 设计](#userspacefilebackend-设计)
- [后端选择和配置](#后端选择和配置)

---

## 存储后端概述

### 设计目标

存储后端模式将文件操作工具的业务逻辑与底层存储实现分离，实现：

1. **可替换性**: 通过配置切换不同的存储实现
2. **测试友好**: 提供内存和本地文件后端用于测试
3. **生产就绪**: 用户空间文件系统后端用于生产环境
4. **扩展性**: 支持依赖注入自定义后端

### 架构层次

```
┌─────────────────────────────────────────────────────┐
│           工具层 (Tool Layer)                        │
│  ReadFileTool | EditFileTool | WriteFileTool        │
└─────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│        存储后端抽象层 (Storage Backend Layer)        │
│         FileOperationsStorageBackend (ABC)          │
└─────────────────────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  Memory      │ │    Local     │ │  UserSpace   │
│  Backend     │ │   Backend    │ │   Backend    │
└──────────────┘ └──────────────┘ └──────────────┘
```

### 参考实现

存储后端模式参考 [`todo`](../../../api/agent/tools/todo/) 工具的实现：

- 抽象基类定义统一接口
- 配置驱动选择后端
- 支持依赖注入扩展

## 抽象接口定义

### FileOperationsStorageBackend

```python
from abc import ABC, abstractmethod
from typing import Literal
from uuid import UUID

class FileOperationsStorageBackend(ABC):
    """
    文件操作存储后端抽象基类

    所有存储后端必须实现此接口，提供统一的文件操作能力。
    """

    def __init__(self, session_id: UUID, user_id: UUID | None = None):
        """
        初始化存储后端。

        Args:
            session_id: 会话 ID，用于数据隔离
            user_id: 用户 ID（可选，某些后端需要）
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
        读取文件内容。

        Args:
            file_path: 文件路径
            offset: 起始行偏移（从0开始），None 表示从头开始
            limit: 最大读取行数，None 表示读到文件末尾

        Returns:
            (content, first_line_number, total_lines)
            - content: 文件内容字符串
            - first_line_number: 第一行的行号（考虑 offset）
            - total_lines: 文件总行数

        Raises:
            FileNotFoundError: 文件不存在
            PermissionError: 无权限访问
            ValueError: 路径无效或包含隐藏组件
        """
        ...

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
        编辑文件内容，替换指定字符串。

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
            DuplicateMatchError: 重复匹配且 replace_all=False
            PermissionError: 无权限编辑
            ValueError: 参数无效
        """
        ...

    # ========== 写入操作 ==========

    @abstractmethod
    async def write_file(
        self,
        file_path: str,
        content: str,
        mode: Literal["create", "overwrite"] = "create"
    ) -> bool:
        """
        写入文件内容。

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
        ...

    # ========== 辅助方法 ==========

    @abstractmethod
    async def file_exists(self, file_path: str) -> bool:
        """检查文件是否存在"""
        ...

    @abstractmethod
    async def delete_file(self, file_path: str) -> bool:
        """删除文件（可选实现）"""
        ...

    @abstractmethod
    async def list_directory(
        self,
        directory_path: str = "."
    ) -> list[str]:
        """列出目录内容（可选实现）"""
        ...
```

### 接口方法说明

#### 必须实现的方法

| 方法 | 用途 | 返回值 |
|------|------|--------|
| `read_file()` | 读取文件内容 | `(content, first_line, total_lines)` |
| `edit_file()` | 编辑文件内容 | `(success, count, updated_content)` |
| `write_file()` | 写入文件内容 | `bool` |
| `file_exists()` | 检查文件是否存在 | `bool` |

#### 可选实现的方法

| 方法 | 用途 | 返回值 |
|------|------|--------|
| `delete_file()` | 删除文件 | `bool` |
| `list_directory()` | 列出目录内容 | `list[str]` |

## MemoryFileBackend 设计

### 概述

内存存储后端，将文件内容存储在进程内存中。适合测试和短期使用。

### 数据结构

```python
from asyncio import Lock
from uuid import UUID
from typing import Dict

class MemoryFileBackend(FileOperationsStorageBackend):
    # 类变量：跨实例共享的内存存储
    _memory_store: Dict[str, Dict[str, str]] = {}
    _lock: Lock = Lock()

    # 存储结构：
    # {
    #     "session_id_1": {
    #         "file1.txt": "content1",
    #         "dir/file2.txt": "content2"
    #     },
    #     "session_id_2": {
    #         "file3.txt": "content3"
    #     }
    # }
```

### 实现要点

#### 并发控制

使用 `asyncio.Lock` 保护内存字典的读写：

```python
async def _get_session_store(self) -> dict[str, str]:
    """获取会话的存储字典"""
    async with self._lock:
        session_key = str(self.session_id)
        if session_key not in self._memory_store:
            self._memory_store[session_key] = {}
        return self._memory_store[session_key]
```

#### read_file 实现

```python
async def read_file(
    self,
    file_path: str,
    offset: int | None = None,
    limit: int | None = None
) -> tuple[str, int, int]:
    store = await self._get_session_store()

    if file_path not in store:
        raise FileNotFoundError(f"文件不存在：{file_path}")

    content = store[file_path]
    lines = content.split('\n')
    total_lines = len(lines)

    # 应用 offset
    start = 0 if offset is None else max(0, offset)
    if start >= total_lines:
        return ("", start + 1, total_lines)

    # 应用 limit
    end = total_lines if limit is None else min(total_lines, start + limit)
    selected_lines = lines[start:end]

    return ('\n'.join(selected_lines), start + 1, total_lines)
```

#### edit_file 实现

```python
async def edit_file(
    self,
    file_path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False
) -> tuple[bool, int, str]:
    store = await self._get_session_store()

    if file_path not in store:
        raise FileNotFoundError(f"文件不存在：{file_path}")

    content = store[file_path]

    # 检查重复
    count = content.count(old_string)
    if count == 0:
        raise ValueError(f"未找到要替换的内容：{old_string}")
    if count > 1 and not replace_all:
        raise ValueError(f"内容重复出现{count}次，请设置 replace_all=true")

    # 执行替换
    if replace_all:
        updated_content = content.replace(old_string, new_string)
    else:
        updated_content = content.replace(old_string, new_string, 1)

    # 更新存储
    async with self._lock:
        store[file_path] = updated_content

    return (True, count, updated_content)
```

#### write_file 实现

```python
async def write_file(
    self,
    file_path: str,
    content: str,
    mode: Literal["create", "overwrite"] = "create"
) -> bool:
    store = await self._get_session_store()

    async with self._lock:
        if file_path in store and mode == "create":
            raise FileExistsError(f"文件已存在：{file_path}")

        # 确保父目录存在（在内存中创建目录条目）
        parent_dir = str(Path(file_path).parent)
        if parent_dir != ".":
            # 可选：为目录创建标记
            store[f"{parent_dir}/.directory"] = ""

        store[file_path] = content

    return True
```

### 特性总结

| 特性 | 支持情况 |
|------|---------|
| 并发安全 | 是（asyncio.Lock） |
| 持久化 | 否（进程重启丢失） |
| 适合场景 | 测试、短期使用 |
| 性能 | 高（内存操作） |

## LocalFileBackend 设计

### 概述

本地文件系统后端，直接操作操作系统的文件系统。适合测试环境。

### 实现要点

#### 基础路径

```python
class LocalFileBackend(FileOperationsStorageBackend):
    def __init__(self, session_id: UUID, base_path: str = "/tmp/file_tools"):
        super().__init__(session_id)
        self.base_path = Path(base_path) / str(session_id)
        self.base_path.mkdir(parents=True, exist_ok=True)
```

#### 异步文件操作

使用 `aiofiles` 进行异步文件操作：

```python
import aiofiles

async def read_file(
    self,
    file_path: str,
    offset: int | None = None,
    limit: int | None = None
) -> tuple[str, int, int]:
    full_path = self._resolve_path(file_path)

    if not full_path.exists():
        raise FileNotFoundError(f"文件不存在：{file_path}")

    async with aiofiles.open(full_path, 'r', encoding='utf-8') as f:
        content = await f.read()

    lines = content.split('\n')
    total_lines = len(lines)

    # 应用 offset 和 limit（与 MemoryFileBackend 相同）
    start = 0 if offset is None else max(0, offset)
    if start >= total_lines:
        return ("", start + 1, total_lines)

    end = total_lines if limit is None else min(total_lines, start + limit)
    selected_lines = lines[start:end]

    return ('\n'.join(selected_lines), start + 1, total_lines)
```

#### 原子写入

```python
import tempfile
import os

async def write_file(
    self,
    file_path: str,
    content: str,
    mode: Literal["create", "overwrite"] = "create"
) -> bool:
    full_path = self._resolve_path(file_path)

    # 确保父目录存在
    full_path.parent.mkdir(parents=True, exist_ok=True)

    # 检查文件是否存在
    if full_path.exists() and mode == "create":
        raise FileExistsError(f"文件已存在：{file_path}")

    # 原子写入
    temp_fd, temp_path = tempfile.mkstemp(
        dir=str(full_path.parent),
        prefix=f".{full_path.name}.tmp"
    )
    try:
        with os.fdopen(temp_fd, 'w') as f:
            f.write(content)
        os.replace(temp_path, str(full_path))
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise

    return True
```

### 特性总结

| 特性 | 支持情况 |
|------|---------|
| 并发安全 | 部分依赖文件系统 |
| 持久化 | 是 |
| 适合场景 | 测试环境 |
| 性能 | 中等（磁盘 I/O） |

## UserSpaceFileBackend 设计

### 概述

用户空间文件系统后端，集成项目的混合文件系统（S3 + PostgreSQL + Redis）。

### 实现要点

#### 初始化

```python
from api.user_space.file_system.fs_utils.file_object import open_file
from api.user_space.file_system.path_utils import (
    build_full_path,
    _path_contains_hidden_component
)
from api.user_space.file_system.sql_stat.utils import get_file_item

class UserSpaceFileBackend(FileOperationsStorageBackend):
    def __init__(self, session_id: UUID, user_id: UUID):
        super().__init__(session_id, user_id)
        if user_id is None:
            raise ValueError("user_id is required for UserSpaceFileBackend")

    def _resolve_path(self, file_path: str) -> Path:
        """解析完整路径并检查隐藏组件"""
        full_path = build_full_path(self.user_id, Path(file_path))

        # 检查隐藏组件
        if _path_contains_hidden_component(full_path, Path(f"/{self.user_id}")):
            raise ValueError(f"路径包含隐藏组件，不允许访问：{file_path}")

        return full_path
```

#### read_file 实现

```python
async def read_file(
    self,
    file_path: str,
    offset: int | None = None,
    limit: int | None = None
) -> tuple[str, int, int]:
    full_path = self._resolve_path(file_path)

    # 检查文件是否存在
    file_item = await get_file_item(self.user_id, full_path)
    if file_item is None or file_item.item_type != "file":
        raise FileNotFoundError(f"文件不存在：{file_path}")

    # 使用 HybridFileObject 读取（自动分布式锁）
    async with open_file(self.user_id, full_path, "r") as f:
        content_bytes = f.read()
        content = content_bytes.decode('utf-8')

    lines = content.split('\n')
    total_lines = len(lines)

    # 应用 offset 和 limit
    start = 0 if offset is None else max(0, offset)
    if start >= total_lines:
        return ("", start + 1, total_lines)

    end = total_lines if limit is None else min(total_lines, start + limit)
    selected_lines = lines[start:end]

    return ('\n'.join(selected_lines), start + 1, total_lines)
```

#### write_file 实现

```python
async def write_file(
    self,
    file_path: str,
    content: str,
    mode: Literal["create", "overwrite"] = "create"
) -> bool:
    full_path = self._resolve_path(file_path)

    # 检查文件是否存在
    file_item = await get_file_item(self.user_id, full_path)
    file_exists = file_item is not None and file_item.item_type == "file"

    if file_exists and mode == "create":
        raise FileExistsError(f"文件已存在：{file_path}")

    # 使用 HybridFileObject 写入（自动分布式锁）
    create_if_missing = (mode == "create")
    async with open_file(
        self.user_id,
        full_path,
        "w",
        create_if_missing=create_if_missing
    ) as f:
        f.write(content.encode('utf-8'))

    return True
```

#### edit_file 实现

```python
async def edit_file(
    self,
    file_path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False
) -> tuple[bool, int, str]:
    full_path = self._resolve_path(file_path)

    # 检查文件是否存在
    file_item = await get_file_item(self.user_id, full_path)
    if file_item is None or file_item.item_type != "file":
        raise FileNotFoundError(f"文件不存在：{file_path}")

    # 读取内容
    async with open_file(self.user_id, full_path, "r") as f:
        content_bytes = f.read()
        content = content_bytes.decode('utf-8')

    # 检查重复
    count = content.count(old_string)
    if count == 0:
        raise ValueError(f"未找到要替换的内容：{old_string}")
    if count > 1 and not replace_all:
        raise ValueError(f"内容重复出现{count}次，请设置 replace_all=true")

    # 执行替换
    if replace_all:
        updated_content = content.replace(old_string, new_string)
    else:
        updated_content = content.replace(old_string, new_string, 1)

    # 写回
    async with open_file(self.user_id, full_path, "r+") as f:
        f.truncate(0)
        f.seek(0)
        f.write(updated_content.encode('utf-8'))

    return (True, count, updated_content)
```

### 特性总结

| 特性 | 支持情况 |
|------|---------|
| 并发安全 | 是（Redis 分布式锁） |
| 持久化 | 是（S3 + PostgreSQL） |
| 适合场景 | 生产环境 |
| 性能 | 取决于 S3 延迟 |
| 隐藏文件限制 | 是 |

## 后端选择和配置

### 配置字段定义

```python
class FileOperationsConfig(SessionToolConfigBase):
    enabled: bool = True

    storage_backend: Literal[
        "memory",
        "local",
        "user_space",
        "kwargs_DI"
    ] = Field(
        default="memory",
        description=(
            "存储后端类型选择。"
            "'memory': 内存存储，适合测试；"
            "'local': 本地文件系统，适合测试环境；"
            "'user_space': 用户空间文件系统，生产环境使用；"
            "'kwargs_DI': 依赖注入，从外部注入存储后端实例。"
        )
    )

    local_base_path: str | None = Field(
        default=None,
        description="本地文件系统的基础路径（仅 storage_backend='local' 时使用）"
    )
```

### 构造器中的后端选择

```python
async def construct_file_operations_tool(
    config: FileOperationsConfig,
    **kwargs
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    session_id = kwargs.get("session_id")
    user_id = kwargs.get("user_id")

    # 根据配置创建存储后端
    if config.storage_backend == "memory":
        from .storage_backend.memory import MemoryFileBackend
        storage_backend = MemoryFileBackend(session_id=session_id)

    elif config.storage_backend == "local":
        from .storage_backend.local import LocalFileBackend
        base_path = config.local_base_path or "/tmp/file_tools"
        storage_backend = LocalFileBackend(
            session_id=session_id,
            base_path=base_path
        )

    elif config.storage_backend == "user_space":
        from .storage_backend.user_space import UserSpaceFileBackend
        if user_id is None:
            raise ValueError("user_id is required for user_space backend")
        storage_backend = UserSpaceFileBackend(
            session_id=session_id,
            user_id=user_id
        )

    elif config.storage_backend == "kwargs_DI":
        storage_backend = kwargs.get("storage_backend")
        if storage_backend is None:
            raise ValueError("storage_backend must be provided when config.storage_backend='kwargs_DI'")

    # 创建工具实例
    tool = ReadFileTool(config=config, storage_backend=storage_backend)
    # 或 EditFileTool, WriteFileTool

    return (GENERATION_TOOL_PARAM, tool)
```

### 后端选择建议

| 场景 | 推荐后端 | 理由 |
|------|---------|------|
| 单元测试 | `memory` | 快速、无副作用 |
| 集成测试 | `local` | 接近真实文件操作 |
| 生产环境 | `user_space` | 完整功能、分布式支持 |
| 自定义场景 | `kwargs_DI` | 灵活扩展 |
