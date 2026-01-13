---
文档标题：storage_backend_base
文档描述：文件操作存储后端的抽象基类定义，包括接口方法、类型注解和文档字符串。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [存储后端抽象概述](#存储后端抽象概述)
- [抽象基类定义](#抽象基类定义)
- [接口方法详细说明](#接口方法详细说明)
- [类型定义](#类型定义)
- [实现示例](#实现示例)

---

## 存储后端抽象概述

### 抽象基类的作用

`FileOperationsStorageBackend` 抽象基类定义了文件操作存储后端的统一接口，其作用包括：

1. **接口规范**: 定义所有存储后端必须实现的方法
2. **类型安全**: 使用 Python 类型注解确保类型一致性
3. **文档契约**: 通过文档字符串说明每个方法的行为
4. **多态支持**: 允许不同存储后端互换使用

### 设计模式

抽象基类使用**策略模式（Strategy Pattern）**：

```
┌─────────────────┐
│   ReadFileTool  │
└────────┬────────┘
         │ 使用
         ▼
┌─────────────────────────────────┐
│ FileOperationsStorageBackend    │  ← 抽象基类
└────────┬────────────────────────┘
         │
    ┌────┴────┬────────────┬─────────────┐
    ▼         ▼            ▼             ▼
┌───────┐ ┌───────┐  ┌──────────┐ ┌──────────┐
│Memory │ │ Local │  │UserSpace │ │  Custom  │
└───────┘ └───────┘  └──────────┘ └──────────┘
```

### 参考实现

参考 [`api/agent/tools/todo/storage_backend/base.py`](../../../api/agent/tools/todo/storage_backend/base.py) 的实现模式。

## 抽象基类定义

### 完整定义

**文件**: `file_operations/storage_backend/base.py`

完整实现请查看：[examples/base_interface_example.py](examples/base_interface_example.py)

### 基类结构

```python
from abc import ABC, abstractmethod
from uuid import UUID
from typing import Literal, Tuple, AsyncIterator


class FileOperationsStorageBackend(ABC):
    """
    文件操作存储后端抽象基类

    定义了所有存储后端必须实现的接口方法。
    """

    def __init__(self, session_id: UUID, user_id: UUID | None = None):
        """
        初始化存储后端

        Args:
            session_id: 会话 ID
            user_id: 用户 ID（可选，某些后端需要）
        """
        self.session_id = session_id
        self.user_id = user_id

    # ==================== 抽象方法 ====================

    @abstractmethod
    async def read_file(
        self,
        file_path: str,
        offset: int | None = None,
        limit: int | None = None
    ) -> Tuple[str, int, int]:
        """
        读取文件内容

        Args:
            file_path: 文件路径
            offset: 起始行偏移（从 0 开始）
            limit: 最大读取行数

        Returns:
            Tuple[str, int, int]: (文件内容, 起始行号, 总行数)

        Raises:
            FileNotFoundError: 文件不存在
            Exception: 其他读取错误
        """
        pass

    @abstractmethod
    async def edit_file(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False
    ) -> Tuple[bool, int, str]:
        """
        编辑文件内容

        Args:
            file_path: 文件路径
            old_string: 要替换的内容
            new_string: 替换后的内容
            replace_all: 是否替换所有匹配项

        Returns:
            Tuple[bool, int, str]: (是否成功, 匹配数量, 消息)

        Raises:
            FileNotFoundError: 文件不存在
            Exception: 其他编辑错误
        """
        pass

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
            mode: 写入模式
                - "create": 创建新文件（文件存在则失败）
                - "overwrite": 覆盖现有文件

        Returns:
            bool: 是否成功

        Raises:
            FileExistsError: 文件已存在（mode="create" 时）
            Exception: 其他写入错误
        """
        pass

    @abstractmethod
    async def file_exists(self, file_path: str) -> bool:
        """
        检查文件是否存在

        Args:
            file_path: 文件路径

        Returns:
            bool: 文件是否存在
        """
        pass
```

## 接口方法详细说明

### read_file()

**用途**: 读取文件内容，支持分页读取

**参数**:
| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `file_path` | `str` | 必填 | 文件路径 |
| `offset` | `int \| None` | `None` | 起始行偏移（从 0 开始）|
| `limit` | `int \| None` | `None` | 最大读取行数 |

**返回值**: `Tuple[str, int, int]`
- `str`: 文件内容
- `int`: 起始行号（用于显示行号）
- `int`: 文件总行数

**行为规范**:
1. 当 `offset` 为 `None` 时，从文件开头读取
2. 当 `limit` 为 `None` 时，读取到文件末尾
3. 当 `offset` 超出文件行数时，返回空字符串
4. 返回的起始行号应为 `offset or 0`
5. 返回的内容应保留原始换行符

**异常**:
- `FileNotFoundError`: 文件不存在
- `Exception`: 其他读取错误（如权限问题）

### edit_file()

**用途**: 编辑文件内容，支持精确替换和全局替换

**参数**:
| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `file_path` | `str` | 必填 | 文件路径 |
| `old_string` | `str` | 必填 | 要替换的内容 |
| `new_string` | `str` | 必填 | 替换后的内容 |
| `replace_all` | `bool` | `False` | 是否替换所有匹配项 |

**返回值**: `Tuple[bool, int, str]`
- `bool`: 是否成功
- `int`: 匹配数量
- `str`: 消息（成功或失败原因）

**行为规范**:
1. 当 `replace_all=False` 时：
   - `old_string` 在文件中唯一出现时，执行替换
   - `old_string` 重复出现时，返回失败（匹配数量 > 1）
   - `old_string` 不存在时，返回失败（匹配数量 = 0）
2. 当 `replace_all=True` 时：
   - 替换所有出现的 `old_string`
   - `old_string` 不存在时，返回失败（匹配数量 = 0）
3. `new_string` 可以为空字符串（相当于删除）

**异常**:
- `FileNotFoundError`: 文件不存在
- `Exception`: 其他编辑错误

### write_file()

**用途**: 写入文件内容，支持创建和覆盖

**参数**:
| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `file_path` | `str` | 必填 | 文件路径 |
| `content` | `str` | 必填 | 文件内容 |
| `mode` | `Literal["create", "overwrite"]` | `"create"` | 写入模式 |

**返回值**: `bool`
- `True`: 写入成功
- `False`: 写入失败

**行为规范**:
1. 当 `mode="create"` 时：
   - 文件不存在：创建文件并写入
   - 文件存在：抛出 `FileExistsError`
2. 当 `mode="overwrite"` 时：
   - 文件不存在：创建文件并写入
   - 文件存在：覆盖文件内容
3. 自动创建父目录（如果不存在）
4. `content` 可以为空字符串（创建空文件）

**异常**:
- `FileExistsError`: 文件已存在（mode="create" 时）
- `Exception`: 其他写入错误

### file_exists()

**用途**: 检查文件是否存在

**参数**:
| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `file_path` | `str` | 必填 | 文件路径 |

**返回值**: `bool`
- `True`: 文件存在
- `False`: 文件不存在

**行为规范**:
1. 不应抛出异常
2. 对于不存在的路径，返回 `False`

## 类型定义

### 返回值类型

```python
from typing import Literal, Tuple

# read_file 返回值
ReadFileResult = Tuple[str, int, int]
# (文件内容, 起始行号, 总行数)

# edit_file 返回值
EditFileResult = Tuple[bool, int, str]
# (是否成功, 匹配数量, 消息)

# write_file 返回值
WriteFileResult = bool
# 是否成功
```

### 模式类型

```python
# write_file 的 mode 参数
WriteMode = Literal["create", "overwrite"]

# storage_backend 配置
StorageBackendType = Literal["memory", "local", "user_space", "kwargs_DI"]
```

## 实现示例

### 实现检查

抽象基类使用 Python 的 `abc` 模块确保子类实现所有抽象方法：

```python
from abc import ABC, abstractmethod

class FileOperationsStorageBackend(ABC):
    @abstractmethod
    async def read_file(self, file_path: str, offset: int | None = None, limit: int | None = None) -> Tuple[str, int, int]:
        pass

# 尝试实例化未完整实现的子类会抛出 TypeError
class IncompleteBackend(FileOperationsStorageBackend):
    async def read_file(self, file_path: str, offset: int | None = None, limit: int | None = None) -> Tuple[str, int, int]:
        return ("", 0, 0)
    # 缺少 edit_file, write_file, file_exists

# 这会抛出 TypeError: Can't instantiate abstract class IncompleteBackend
# with abstract methods edit_file, file_exists, write_file
```

### 类型检查

使用 `isinstance()` 检查实例类型：

```python
from file_operations.storage_backend.base import FileOperationsStorageBackend

def use_storage_backend(backend: FileOperationsStorageBackend):
    # 类型检查
    if not isinstance(backend, FileOperationsStorageBackend):
        raise TypeError(f"期望 FileOperationsStorageBackend，得到 {type(backend)}")

    # 使用
    content, first, total = await backend.read_file("test.txt")
```

### 完整示例

完整实现示例请查看：[examples/base_interface_example.py](examples/base_interface_example.py)

### 子类实现模板

```python
from .base import FileOperationsStorageBackend

class MyCustomBackend(FileOperationsStorageBackend):
    """自定义存储后端示例"""

    def __init__(self, session_id: UUID, user_id: UUID | None = None):
        super().__init__(session_id, user_id)
        # 初始化自定义资源
        self.custom_resource = ...

    async def read_file(
        self,
        file_path: str,
        offset: int | None = None,
        limit: int | None = None
    ) -> Tuple[str, int, int]:
        # 实现读取逻辑
        content = ...
        first_line = offset or 0
        total_lines = ...
        return (content, first_line, total_lines)

    async def edit_file(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False
    ) -> Tuple[bool, int, str]:
        # 实现编辑逻辑
        ...
        return (success, match_count, message)

    async def write_file(
        self,
        file_path: str,
        content: str,
        mode: Literal["create", "overwrite"] = "create"
    ) -> bool:
        # 实现写入逻辑
        ...
        return True

    async def file_exists(self, file_path: str) -> bool:
        # 实现存在检查
        ...
        return True
```
