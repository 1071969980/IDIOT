---
文档标题：write_file_tool_design
文档描述：write_file 工具的概念设计，包括参数定义、存储后端接口需求、文件创建和覆盖逻辑以及错误处理。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [工具概述](#工具概述)
- [参数定义](#参数定义)
- [存储后端接口需求](#存储后端接口需求)
- [文件创建和覆盖逻辑](#文件创建和覆盖逻辑)
- [错误处理](#错误处理)
- [使用示例](#使用示例)

---

## 工具概述

**工具名称**: `write_file`

**功能描述**: 向指定文件写入内容。支持创建新文件或覆盖现有文件。

**使用场景**:
- Agent 需要创建新的代码文件
- Agent 需要生成配置文件
- Agent 需要保存处理结果到文件
- Agent 需要完全替换文件内容

**工具行为**:
1. 验证参数（file_path, content, mode）
2. 检查文件是否存在
3. 根据 `mode` 参数处理：
   - `create`: 仅当文件不存在时创建
   - `overwrite`: 允许覆盖现有文件
4. 写入内容
5. 返回操作结果

**设计原则**:
- **显式意图**: 覆盖现有文件需要显式设置 `mode="overwrite"`
- **目录自动创建**: 如果父目录不存在，自动创建
- **原子写入**: 尽量保证写入操作的原子性

## 参数定义

### WriteFileParamDefine

```python
class WriteFileParamDefine(BaseModel):
    file_path: str = Field(
        description="要写入的文件路径。相对于用户工作目录的路径。"
    )
    content: str = Field(
        description="要写入文件的内容。"
    )
    mode: Literal["create", "overwrite"] = Field(
        default="create",
        description=(
            "写入模式。"
            "'create': 仅创建新文件，如果文件已存在则返回错误。"
            "'overwrite': 允许覆盖现有文件。"
        )
    )

    model_config = ConfigDict(extra='allow')
```

### 参数说明

| 参数 | 类型 | 默认值 | 必需 | 描述 |
|------|------|--------|------|------|
| `file_path` | `str` | - | 是 | 要写入的文件路径 |
| `content` | `str` | - | 是 | 要写入文件的内容 |
| `mode` | `Literal["create", "overwrite"]` | `"create"` | 否 | 写入模式 |

### 参数验证规则

1. **file_path**:
   - 不能为空字符串
   - 必须是有效的文件路径格式
   - 对于 UserSpaceFileBackend，不能包含隐藏组件

2. **content**:
   - 可以为空字符串（创建空文件）

3. **mode**:
   - 必须是 `"create"` 或 `"overwrite"`
   - 默认为 `"create"`（安全默认值）

### mode 参数详解

| mode | 文件不存在 | 文件存在 | 行为 |
|------|-----------|---------|------|
| `"create"` | 创建文件 | 返回错误 | 安全模式，防止意外覆盖 |
| `"overwrite"` | 创建文件 | 覆盖文件 | 允许覆盖，需要显式设置 |

## 存储后端接口需求

### 抽象接口方法

存储后端必须实现以下方法：

```python
class FileOperationsStorageBackend(ABC):
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
            content: 要写入的内容
            mode: 写入模式
                - "create": 仅创建新文件
                - "overwrite": 允许覆盖现有文件

        Returns:
            True 如果写入成功

        Raises:
            FileExistsError: 文件已存在且 mode="create"
            FileNotFoundError: 父目录不存在且无法创建（某些后端）
            PermissionError: 无权限写入文件
            ValueError: 路径包含隐藏组件或参数无效
        """
        ...
```

### 返回值说明

返回 `bool`：
- `True`: 写入成功

### 存储后端实现要点

#### MemoryFileBackend

- 检查文件是否已存在（根据 mode）
- 如果允许，更新内存字典中的内容
- 确保操作原子性（使用锁）

#### LocalFileBackend

- 检查文件是否存在（根据 mode）
- 自动创建父目录（使用 `Path.mkdir(parents=True, exist_ok=True)`）
- 使用 `aiofiles` 异步写入文件
- 原子性写入（先写临时文件，再重命名）

#### UserSpaceFileBackend

- 检查文件是否存在（通过文件系统查询）
- 使用 `open_file()` 以写入模式打开文件
- `create_if_missing=True` 参数自动处理创建
- 自动处理分布式锁
- 检查隐藏文件路径

## 文件创建和覆盖逻辑

### 决策树

```
开始
  │
  ├─ 检查文件是否存在
  │   │
  │   ├─ 文件不存在
  │   │   │
  │   │   └─ 创建父目录（如需要）
  │   │       │
  │   │       └─ 写入内容
  │   │           │
  │   │           └─ 返回成功
  │   │
  │   └─ 文件存在
  │       │
  │       ├─ mode = "create"
  │       │   │
  │       │   └─ 返回错误：文件已存在
  │       │
  │       └─ mode = "overwrite"
  │           │
  │           └─ 覆盖文件内容
  │               │
  │               └─ 返回成功
```

### 目录自动创建

对于所有存储后端，如果父目录不存在，应该自动创建：

```python
async def ensure_parent_directory(file_path: str) -> None:
    """确保父目录存在"""
    parent_dir = str(Path(file_path).parent)
    if parent_dir and parent_dir != ".":
        # 根据存储后端类型创建目录
        # MemoryFileBackend: 在内存中创建目录结构
        # LocalFileBackend: 使用 os.makedirs 或 Path.mkdir
        # UserSpaceFileBackend: 使用文件系统的目录创建功能
        ...
```

### 原子写入策略

#### LocalFileBackend 原子写入

```python
import tempfile
import shutil
from pathlib import Path

async def atomic_write(file_path: str, content: str) -> None:
    """原子性写入文件"""
    # 1. 写入临时文件
    temp_fd, temp_path = tempfile.mkstemp(
        dir=str(Path(file_path).parent),
        prefix=f".{Path(file_path).name}.tmp"
    )
    try:
        with os.fdopen(temp_fd, 'w') as f:
            f.write(content)
        # 2. 原子性重命名
        os.replace(temp_path, file_path)
    except Exception:
        # 3. 清理临时文件
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
```

#### UserSpaceFileBackend 原子写入

`HybridFileObject` 的上下文管理器已经提供了原子性保证：

```python
async with open_file(user_id, Path(file_path), "w", create_if_missing=True) as f:
    f.write(content.encode('utf-8'))
# 退出上下文时自动提交更改
```

### 模式检查伪代码

```python
async def write_file_with_mode_check(
    storage_backend,
    file_path: str,
    content: str,
    mode: str
) -> tuple[bool, str]:
    """根据模式写入文件"""
    file_exists = await storage_backend.file_exists(file_path)

    if file_exists:
        if mode == "create":
            return False, f"文件已存在：{file_path}。如要覆盖，请设置 mode='overwrite'"
        # mode == "overwrite"，继续执行

    # 执行写入
    await storage_backend._write_content(file_path, content)
    return True, f"成功写入文件：{file_path}"
```

## 错误处理

### 参数验证错误

| 错误 | 消息 | 处理 |
|------|------|------|
| `file_path` 为空 | "file_path 不能为空" | 返回 `occur_error=True` |
| `mode` 无效 | "mode 必须是 'create' 或 'overwrite'" | 返回 `occur_error=True` |
| 路径包含隐藏组件 | "路径包含隐藏组件，不允许访问" | 返回 `occur_error=True` |

### 文件操作错误

| 错误 | 消息 | 处理 |
|------|------|------|
| `FileExistsError` | "文件已存在：{file_path}。如要覆盖，请设置 mode='overwrite'" | 返回 `occur_error=True` |
| `PermissionError` | "无权限写入文件：{file_path}" | 返回 `occur_error=True` |
| 父目录创建失败 | "无法创建父目录：{parent_dir}" | 返回 `occur_error=True` |
| 写入失败 | "写入文件时发生错误：{error}" | 返回 `occur_error=True` |

### UserSpaceFileBackend 特定错误

| 错误 | 消息 | 处理 |
|------|------|------|
| 路径是目录 | "{file_path} 是一个目录，不能作为文件写入" | 返回 `occur_error=True` |
| S3 上传失败 | "文件内容上传到 S3 失败：{error}" | 返回 `occur_error=True` |
| 数据库记录失败 | "文件元数据记录失败：{error}" | 返回 `occur_error=True` |

### 成功返回格式

```python
def format_success_message(file_path: str, mode: str, bytes_written: int) -> str:
    """格式化成功消息"""
    if mode == "create":
        return f"成功创建文件：{file_path}（{bytes_written} 字节）"
    else:
        return f"成功覆盖文件：{file_path}（{bytes_written} 字节）"

return ToolTaskResult(
    str_content=format_success_message(file_path, mode, len(content.encode('utf-8'))),
    occur_error=False,
)
```

### 错误返回格式

```python
return ToolTaskResult(
    str_content=f"写入文件失败：{error_message}",
    occur_error=True,
)
```

## 使用示例

### 示例 1：创建新文件（默认模式）

```python
# 调用
result = await write_file_tool(
    file_path="src/new_module.py",
    content='''def hello():
    print("Hello, World!")
'''
)

# 输出
"""
成功创建文件：src/new_module.py（45 字节）
"""
```

### 示例 2：覆盖现有文件

```python
# 调用
result = await write_file_tool(
    file_path="config/settings.json",
    content='{"version": "2.0"}',
    mode="overwrite"
)

# 输出
"""
成功覆盖文件：config/settings.json（20 字节）
"""
```

### 示例 3：文件已存在（错误）

```python
# 调用
result = await write_file_tool(
    file_path="src/existing.py",
    content="# new content",
    mode="create"  # 默认，文件已存在
)

# 输出
"""
写入文件失败：文件已存在：src/existing.py。
如要覆盖，请设置 mode='overwrite'
"""
```

### 示例 4：创建空文件

```python
# 调用
result = await write_file_tool(
    file_path="logs/empty.log",
    content=""  # 空内容
)

# 输出
"""
成功创建文件：logs/empty.log（0 字节）
"""
```

### 示例 5：自动创建父目录

```python
# 调用
result = await write_file_tool(
    file_path="deep/nested/path/config.yaml",
    content="key: value"
)

# 输出（自动创建 deep/nested/path 目录）
"""
成功创建文件：deep/nested/path/config.yaml（11 字节）
"""
```

### 示例 6：写入大文件

```python
# 调用
large_content = generate_large_content()  # 假设生成 1MB 内容
result = await write_file_tool(
    file_path="data/large_dataset.json",
    content=large_content,
    mode="overwrite"
)

# 输出
"""
成功覆盖文件：data/large_dataset.json（1048576 字节）
"""
```
