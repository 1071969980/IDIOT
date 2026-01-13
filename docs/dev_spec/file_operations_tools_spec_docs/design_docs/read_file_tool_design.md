---
文档标题：read_file_tool_design
文档描述：read_file 工具的概念设计，包括参数定义、存储后端接口需求、输出格式和错误处理。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [工具概述](#工具概述)
- [参数定义](#参数定义)
- [存储后端接口需求](#存储后端接口需求)
- [输出格式规范](#输出格式规范)
- [错误处理](#错误处理)
- [使用示例](#使用示例)

---

## 工具概述

**工具名称**: `read_file`

**功能描述**: 读取指定文件的内容，支持从指定行开始读取、限制读取行数，以及显示行号。

**使用场景**:
- Agent 需要查看代码文件内容
- Agent 需要读取配置文件
- Agent 需要检查文档内容
- Agent 需要分析日志文件

**工具行为**:
1. 验证 `file_path` 参数
2. 调用存储后端的 `read_file()` 方法
3. 根据参数处理偏移量和行数限制
4. 格式化输出（可选显示行号）
5. 返回 `ToolTaskResult`

## 参数定义

### ReadFileParamDefine

```python
class ReadFileParamDefine(BaseModel):
    file_path: str = Field(
        description="要读取的文件路径。相对于用户工作目录的路径。"
    )
    offset: int | None = Field(
        default=None,
        description=(
            "起始行的偏移量（从0开始）。如果为 None，从文件开头开始读取。"
            "例如，offset=10 表示从第11行开始读取。"
        )
    )
    limit: int | None = Field(
        default=None,
        description=(
            "要读取的最大行数。如果为 None，读取到文件末尾。"
            "例如，limit=100 表示最多读取100行。"
        )
    )
    show_line_numbers: bool = Field(
        default=False,
        description="是否在输出中显示行号。如果为 True，每行前面会添加行号。"
    )

    model_config = ConfigDict(extra='allow')
```

### 参数说明

| 参数 | 类型 | 默认值 | 必需 | 描述 |
|------|------|--------|------|------|
| `file_path` | `str` | - | 是 | 要读取的文件路径，相对于用户工作目录 |
| `offset` | `int \| None` | `None` | 否 | 起始行偏移量（从0开始），None 表示从文件开头 |
| `limit` | `int \| None` | `None` | 否 | 最大读取行数，None 表示读取到文件末尾 |
| `show_line_numbers` | `bool` | `False` | 否 | 是否显示行号 |

### 参数验证规则

1. **file_path**:
   - 不能为空字符串
   - 必须是有效的文件路径格式
   - 对于 UserSpaceFileBackend，不能包含隐藏组件

2. **offset**:
   - 如果提供，必须大于等于 0
   - 超出文件行数时返回空内容或提示

3. **limit**:
   - 如果提供，必须大于 0
   - 与 offset 结合使用时，从 offset 开始最多读取 limit 行

4. **show_line_numbers**:
   - 布尔值，默认 false

## 存储后端接口需求

### 抽象接口方法

存储后端必须实现以下方法：

```python
class FileOperationsStorageBackend(ABC):
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
            offset: 起始行偏移（从0开始），None 表示从文件开头
            limit: 最大读取行数，None 表示读取到文件末尾

        Returns:
            (content, first_line_number, total_lines)
            - content: 文件内容（字符串）
            - first_line_number: 第一行的行号（从1开始，考虑 offset）
            - total_lines: 文件总行数（用于提示用户）

        Raises:
            FileNotFoundError: 文件不存在
            PermissionError: 无权限访问文件
            ValueError: 路径包含隐藏组件（UserSpaceFileBackend）
        """
        ...
```

### 返回值说明

返回三元组 `(content, first_line_number, total_lines)`：

- **content**: 实际读取的文件内容（字符串），已应用 offset 和 limit
- **first_line_number**: 第一行的行号（从1开始），用于显示行号时计算
- **total_lines**: 文件总行数，用于在返回信息中提示用户

### 存储后端实现要点

#### MemoryFileBackend

- 从内存字典中获取文件内容
- 按行分割内容
- 应用 offset 和 limit
- 返回处理后的内容

#### LocalFileBackend

- 使用 `aiofiles` 异步读取文件
- 处理文件不存在错误
- 按行分割并应用 offset/limit

#### UserSpaceFileBackend

- 使用 `open_file()` 打开文件
- 自动处理分布式锁
- 检查隐藏文件路径（调用前检查）
- 读取内容并应用 offset/limit

## 输出格式规范

### 无行号模式 (show_line_numbers=False)

```
文件内容：test.py
读取行数：1-50 / 共120行

def hello_world():
    print("Hello, World!")
    return True
```

### 带行号模式 (show_line_numbers=True)

```
文件内容：test.py
读取行数：1-50 / 共120行

     1→def hello_world():
     2→    print("Hello, World!")
     3→    return True
```

### 输出格式化逻辑

```python
async def _format_output(
    content: str,
    file_path: str,
    first_line_number: int,
    last_line_number: int,
    total_lines: int,
    show_line_numbers: bool
) -> str:
    """格式化输出内容"""
    lines = content.split('\n')

    if show_line_numbers:
        # 计算行号宽度
        max_line_number = last_line_number
        line_number_width = len(str(max_line_number))
        # 添加行号
        numbered_lines = [
            f"{i + first_line_number:>{line_number_width}}→{line}"
            for i, line in enumerate(lines)
        ]
        content = '\n'.join(numbered_lines)

    header = (
        f"文件内容：{file_path}\n"
        f"读取行数：{first_line_number}-{last_line_number} / 共{total_lines}行\n"
    )

    return header + "\n" + content
```

### 特殊情况处理

1. **文件为空**：
   ```
   文件内容：test.py
   文件为空
   ```

2. **offset 超出文件行数**：
   ```
   文件内容：test.py
   起始行超出文件范围（文件共50行，offset=100）
   ```

3. **部分读取（limit 小于剩余行数）**：
   ```
   文件内容：test.py
   读取行数：101-150 / 共500行
   （显示更多内容可用 offset=150, limit=... 继续读取）
   ```

## 错误处理

### 参数验证错误

| 错误 | 消息 | 处理 |
|------|------|------|
| `file_path` 为空 | "file_path 不能为空" | 返回 `occur_error=True` |
| `offset < 0` | "offset 必须大于等于 0" | 返回 `occur_error=True` |
| `limit <= 0` | "limit 必须大于 0" | 返回 `occur_error=True` |
| 路径包含隐藏组件 | "路径包含隐藏组件，不允许访问" | 返回 `occur_error=True` |

### 存储后端错误

| 错误 | 消息 | 处理 |
|------|------|------|
| `FileNotFoundError` | "文件 '{file_path}' 不存在" | 返回 `occur_error=True` |
| `PermissionError` | "无权限访问文件 '{file_path}'" | 返回 `occur_error=True` |
| `IsADirectoryError` | "'{file_path}' 是一个目录，不是文件" | 返回 `occur_error=True` |
| 其他异常 | "读取文件时发生错误：{error}" | 返回 `occur_error=True` |

### 错误返回格式

```python
return ToolTaskResult(
    str_content=f"读取文件失败：{error_message}",
    occur_error=True,
)
```

## 使用示例

### 示例 1：读取整个文件

```python
# 调用
result = await read_file_tool(
    file_path="src/main.py"
)

# 输出
"""
文件内容：src/main.py
读取行数：1-100 / 共100行

import sys
def main():
    print("Hello")
...
"""
```

### 示例 2：读取部分内容（带行号）

```python
# 调用
result = await read_file_tool(
    file_path="src/main.py",
    offset=10,
    limit=20,
    show_line_numbers=True
)

# 输出
"""
文件内容：src/main.py
读取行数：11-30 / 共100行

    11→def process_data(data):
    12→    result = []
    13→    for item in data:
...
    30→    return result
"""
```

### 示例 3：读取配置文件

```python
# 调用
result = await read_file_tool(
    file_path="config/settings.yaml"
)

# 输出
"""
文件内容：config/settings.yaml
读取行数：1-15 / 共15行

database:
  host: localhost
  port: 5432
...
"""
```

更多示例请参考：[design_docs/examples/read_file_example.py](examples/read_file_example.py)
