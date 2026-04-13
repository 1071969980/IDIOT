---
文档标题：directory_structure
文档描述：文件操作工具的完整目录结构设计，包括文件职责划分和模块依赖关系。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [目录结构概览](#目录结构概览)
- [工具目录结构](#工具目录结构)
- [文件职责说明](#文件职责说明)
- [模块依赖关系](#模块依赖关系)
- [与现有系统的集成](#与现有系统的集成)

---

## 目录结构概览

### 完整目录树

```
api/agent/tools/
├── config_data_model.py                      # 工具配置基类（已存在）
├── data_model.py                             # 工具数据模型（已存在）
├── type.py                                   # 类型定义（已存在）
├── tool_factory/
│   ├── tool_factory.py                       # 工具工厂（已存在）
│   └── tool_init_function.py                 # 工具注册（需修改）
│
└── file_operations/                          # 文件操作工具目录（新建）
    ├── __init__.py                           # 包文件
    │
    ├── storage_backend/                      # 存储后端（三个工具共享）
    │   ├── __init__.py
    │   ├── base.py                           # 抽象基类
    │   ├── memory.py                         # 内存存储
    │   ├── local.py                          # 本地文件存储
    │   └── user_space.py                     # 用户空间文件系统
    │
    ├── read_file/                            # read_file 工具目录
    │   ├── __init__.py
    │   ├── config_data_model.py              # 配置和参数定义
    │   └── constructor.py                    # 构造器
    │
    ├── edit_file/                            # edit_file 工具目录
    │   ├── __init__.py
    │   ├── config_data_model.py              # 配置和参数定义
    │   ├── constructor.py                    # 构造器
    │   └── utils.py                          # 现有工具函数（保留）
    │
    └── write_file/                           # write_file 工具目录
        ├── __init__.py
        ├── config_data_model.py              # 配置和参数定义
        └── constructor.py                    # 构造器
```

### 设计说明

#### 1. 统一的工具目录

三个文件操作工具（`read_file`, `edit_file`, `write_file`）归纳在 `file_operations` 目录下，具有以下优点：

- **逻辑聚合**: 相关功能组织在一起
- **命名空间隔离**: 避免与其他工具冲突
- **易于维护**: 集中管理文件操作相关的代码

#### 2. 共享的存储后端

`storage_backend` 位于 `file_operations` 的直接子目录，三个工具共享使用：

- **代码复用**: 避免在多个工具中重复存储后端代码
- **统一接口**: 确保所有工具使用相同的存储后端抽象
- **易于扩展**: 新增存储后端只需在一处修改

#### 3. 工具目录简洁

每个工具目录只包含其特定内容：
- `config_data_model.py`: 工具特定的配置和参数定义
- `constructor.py`: 工具类和构造器函数
- `utils.py`: 可选的工具函数（仅 edit_file 有）

## 工具目录结构

### file_operations 目录

```
api/agent/tools/file_operations/
├── __init__.py                               # 包文件
│   └── # 导出工具名称或初始化
│
├── storage_backend/                          # 共享存储后端
│   ├── __init__.py
│   │   └── from .base import FileOperationsStorageBackend
│   ├── base.py                               # 抽象基类
│   ├── memory.py                             # 内存存储
│   ├── local.py                              # 本地文件存储
│   └── user_space.py                         # 用户空间文件系统
│
├── read_file/                                # read_file 工具
│   ├── __init__.py
│   ├── config_data_model.py
│   └── constructor.py
│
├── edit_file/                                # edit_file 工具
│   ├── __init__.py
│   ├── config_data_model.py
│   ├── constructor.py
│   └── utils.py
│
└── write_file/                               # write_file 工具
    ├── __init__.py
    ├── config_data_model.py
    └── constructor.py
```

### read_file 目录

```
api/agent/tools/file_operations/read_file/
├── __init__.py
│   └── from .constructor import CONSTRUCTOR
├── config_data_model.py
│   ├── TOOL_NAME = "read_file"
│   ├── class ReadFileConfig(...)
│   ├── class ReadFileParamDefine(...)
│   ├── READ_FILE_GENERATION_TOOL_PARAM = ...
│   └── DEFAULT_TOOL_CONFIG = {...}
└── constructor.py
    ├── class ReadFileTool(...)
    ├── def construct_read_file(...)
    └── CONSTRUCTOR = {"read_file": construct_read_file}
```

### edit_file 目录

```
api/agent/tools/file_operations/edit_file/
├── __init__.py
│   └── from .constructor import CONSTRUCTOR
├── config_data_model.py
│   ├── TOOL_NAME = "edit_file"
│   ├── class EditFileConfig(...)
│   ├── class EditFileParamDefine(...)
│   ├── EDIT_FILE_GENERATION_TOOL_PARAM = ...
│   └── DEFAULT_TOOL_CONFIG = {...}
├── constructor.py
│   ├── class EditFileTool(...)
│   ├── def construct_edit_file(...)
│   └── CONSTRUCTOR = {"edit_file": construct_edit_file}
└── utils.py
    └── def edit_string(...)  # 现有函数，可被工具类调用
```

### write_file 目录

```
api/agent/tools/file_operations/write_file/
├── __init__.py
│   └── from .constructor import CONSTRUCTOR
├── config_data_model.py
│   ├── TOOL_NAME = "write_file"
│   ├── class WriteFileConfig(...)
│   ├── class WriteFileParamDefine(...)
│   ├── WRITE_FILE_GENERATION_TOOL_PARAM = ...
│   └── DEFAULT_TOOL_CONFIG = {...}
└── constructor.py
    ├── class WriteFileTool(...)
    ├── def construct_write_file(...)
    └── CONSTRUCTOR = {"write_file": construct_write_file}
```

## 文件职责说明

### storage_backend/base.py

**职责**：定义存储后端抽象基类

**内容**：
- `FileOperationsStorageBackend` 抽象基类
- 抽象方法：`read_file()`, `edit_file()`, `write_file()`, `file_exists()`

**示例**：

```python
# api/agent/tools/file_operations/storage_backend/base.py

from abc import ABC, abstractmethod
from uuid import UUID
from typing import Literal, Tuple

class FileOperationsStorageBackend(ABC):
    """文件操作存储后端抽象基类"""

    def __init__(self, session_id: UUID, user_id: UUID | None = None):
        self.session_id = session_id
        self.user_id = user_id

    @abstractmethod
    async def read_file(
        self,
        file_path: str,
        offset: int | None = None,
        limit: int | None = None
    ) -> Tuple[str, int, int]:
        """读取文件内容"""
        ...

    @abstractmethod
    async def edit_file(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False
    ) -> Tuple[bool, int, str]:
        """编辑文件内容"""
        ...

    @abstractmethod
    async def write_file(
        self,
        file_path: str,
        content: str,
        mode: Literal["create", "overwrite"] = "create"
    ) -> bool:
        """写入文件内容"""
        ...

    @abstractmethod
    async def file_exists(self, file_path: str) -> bool:
        """检查文件是否存在"""
        ...
```

### storage_backend/memory.py

**职责**：实现内存存储后端

**内容**：
- `MemoryFileBackend` 类
- 类变量 `_memory_store` 和 `_lock`
- 实现所有抽象方法

### storage_backend/local.py

**职责**：实现本地文件系统存储后端

**内容**：
- `LocalFileBackend` 类
- 使用 `aiofiles` 进行异步文件操作
- 实现所有抽象方法

### storage_backend/user_space.py

**职责**：实现用户空间文件系统存储后端

**内容**：
- `UserSpaceFileBackend` 类
- 集成 `HybridFileObject`
- 隐藏文件检测
- 实现所有抽象方法

### read_file/constructor.py

**职责**：实现 read_file 工具类和构造器

**内容**：
- `ReadFileTool` 类
- `construct_read_file()` 函数
- `CONSTRUCTOR` 字典

**示例**：

```python
# api/agent/tools/file_operations/read_file/constructor.py

from uuid import UUID
from typing import Any
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

from .config_data_model import (
    ReadFileConfig,
    ReadFileParamDefine,
    READ_FILE_GENERATION_TOOL_PARAM
)
from ..storage_backend.base import FileOperationsStorageBackend
from ..storage_backend.memory import MemoryFileBackend
# ... 其他存储后端导入

class ReadFileTool:
    def __init__(self, config: ReadFileConfig, storage_backend: FileOperationsStorageBackend):
        self.config = config
        self.storage_backend = storage_backend

    async def __call__(self, **kwargs: dict[str, Any]):
        # 工具实现
        ...

def construct_read_file(
    config: ReadFileConfig,
    **kwargs: dict[str, Any]
) -> tuple[ChatCompletionToolParam, Any]:
    # 构造器实现
    ...

CONSTRUCTOR = {"read_file": construct_read_file}
```

### edit_file/constructor.py

**职责**：实现 edit_file 工具类和构造器

结构类似 `read_file/constructor.py`，但实现编辑逻辑。

### write_file/constructor.py

**职责**：实现 write_file 工具类和构造器

结构类似 `read_file/constructor.py`，但实现写入逻辑。

## 模块依赖关系

### 依赖图

```
┌─────────────────────────────────────────────────────────┐
│                    工具注册层                            │
│    tool_factory/tool_init_function.py (需修改)          │
└────────────────────┬────────────────────────────────────┘
                     │ 导入 CONSTRUCTOR
                     ▼
┌─────────────────────────────────────────────────────────┐
│                    构造器层                              │
│    file_operations/read_file/constructor.py             │
│    file_operations/edit_file/constructor.py             │
│    file_operations/write_file/constructor.py            │
└────────────────────┬────────────────────────────────────┘
                     │ 创建实例
                     ▼
┌─────────────────────────────────────────────────────────┐
│                    工具层                                │
│    ReadFileTool | EditFileTool | WriteFileTool          │
└────────────────────┬────────────────────────────────────┘
                     │ 调用
                     ▼
┌─────────────────────────────────────────────────────────┐
│                  存储后端层                              │
│    file_operations/storage_backend/base.py (抽象基类)   │
│           │            │            │                   │
│           ▼            ▼            ▼                   │
│       memory.py    local.py   user_space.py              │
└─────────────────────────────────────────────────────────┘
                     │ 依赖
                     ▼
┌─────────────────────────────────────────────────────────┐
│                   基础设施层                              │
│  - api.agent.tools.config_data_model (配置基类)         │
│  - api.agent.tools.data_model (ToolTaskResult)          │
│  - api.agent.tools.type (ToolClosure)                   │
│  - api.user_space.file_system (用户空间文件系统)        │
│  - pydantic (参数验证)                                   │
│  - aiofiles (异步文件操作)                              │
└─────────────────────────────────────────────────────────┘
```

### 导入关系

#### 从工具导入存储后端

```python
# read_file/constructor.py
from ..storage_backend.base import FileOperationsStorageBackend
from ..storage_backend.memory import MemoryFileBackend
from ..storage_backend.local import LocalFileBackend
from ..storage_backend.user_space import UserSpaceFileBackend
```

#### 相对导入说明

```
file_operations/
├── storage_backend/
│   └── base.py
└── read_file/
    └── constructor.py
```

从 `read_file/constructor.py` 导入 `storage_backend`：

```python
# .. 表示上一级目录（file_operations）
from ..storage_backend.base import FileOperationsStorageBackend
```

### 包初始化

#### file_operations/__init__.py

```python
# api/agent/tools/file_operations/__init__.py

"""
文件操作工具包

包含 read_file, edit_file, write_file 三个工具及其共享的存储后端。
"""

__all__ = [
    "read_file",
    "edit_file",
    "write_file"
]
```

#### storage_backend/__init__.py

```python
# api/agent/tools/file_operations/storage_backend/__init__.py

"""
文件操作存储后端

提供统一的存储后端接口，支持内存、本地文件系统和用户空间文件系统。
"""

from .base import FileOperationsStorageBackend
from .memory import MemoryFileBackend
from .local import LocalFileBackend
from .user_space import UserSpaceFileBackend

__all__ = [
    "FileOperationsStorageBackend",
    "MemoryFileBackend",
    "LocalFileBackend",
    "UserSpaceFileBackend"
]
```

## 与现有系统的集成

### 工具注册

修改 [`tool_factory/tool_init_function.py`](../../../api/agent/tools/tool_factory/tool_init_function.py)：

```python
# 注意路径变化：从 read_file 变为 file_operations.read_file
from api.agent.tools.file_operations.read_file.constructor import CONSTRUCTOR as READ_FILE_CONSTRUCTOR
from api.agent.tools.file_operations.edit_file.constructor import CONSTRUCTOR as EDIT_FILE_CONSTRUCTOR
from api.agent.tools.file_operations.write_file.constructor import CONSTRUCTOR as WRITE_FILE_CONSTRUCTOR

TOOL_INIT_FUNCTIONS: dict[str, Callable[..., tuple[ChatCompletionToolParam, ToolClosure]]] = {
    **ASK_USER_CONSTRUCTOR,
    **TODO_WRITE_CONSTRUCTOR,
    **READ_FILE_CONSTRUCTOR,
    **EDIT_FILE_CONSTRUCTOR,
    **WRITE_FILE_CONSTRUCTOR,
}
```

### 默认配置

修改 [`session_agent_config/config_data_model.py`](../../../api/agent/session_agent_config/config_data_model.py)：

```python
# 注意路径变化
from api.agent.tools.file_operations.read_file.config_data_model import DEFAULT_TOOL_CONFIG as READ_FILE_DEFAULT_CONFIG
from api.agent.tools.file_operations.edit_file.config_data_model import DEFAULT_TOOL_CONFIG as EDIT_FILE_DEFAULT_CONFIG
from api.agent.tools.file_operations.write_file.config_data_model import DEFAULT_TOOL_CONFIG as WRITE_FILE_DEFAULT_CONFIG

DEFAULT_TOOLS_CONFIG: dict[str, SessionToolConfigBase] = {
    **ASK_USER_DEFAULT_CONFIG,
    **TODO_WRITE_DEFAULT_CONFIG,
    **READ_FILE_DEFAULT_CONFIG,
    **EDIT_FILE_DEFAULT_CONFIG,
    **WRITE_FILE_DEFAULT_CONFIG,
}
```

### 用户空间文件系统集成

`storage_backend/user_space.py` 直接使用现有的用户空间文件系统：

```python
# api/agent/tools/file_operations/storage_backend/user_space.py

from api.user_space.file_system.fs_utils.file_object import open_file
from api.user_space.file_system.path_utils import (
    build_full_path,
    _path_contains_hidden_component
)
from api.user_space.file_system.sql_stat.utils import get_file_item
```

### 创建目录的命令

```bash
# 创建 file_operations 目录结构
cd api/agent/tools
mkdir -p file_operations/storage_backend
mkdir -p file_operations/read_file
mkdir -p file_operations/edit_file
mkdir -p file_operations/write_file

# 创建 __init__.py 文件
touch file_operations/__init__.py
touch file_operations/storage_backend/__init__.py
touch file_operations/read_file/__init__.py
touch file_operations/edit_file/__init__.py
touch file_operations/write_file/__init__.py
```
