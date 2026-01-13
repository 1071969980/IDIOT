---
文档标题：edit_file_tool_design
文档描述：edit_file 工具的概念设计，包括参数定义、存储后端接口需求、重复内容检测逻辑和错误处理。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [工具概述](#工具概述)
- [参数定义](#参数定义)
- [存储后端接口需求](#存储后端接口需求)
- [重复内容检测逻辑](#重复内容检测逻辑)
- [错误处理](#错误处理)
- [使用示例](#使用示例)

---

## 工具概述

**工具名称**: `edit_file`

**功能描述**: 编辑文件内容，通过替换指定的字符串实现。支持单次替换或全局替换。

**使用场景**:
- Agent 需要修改代码文件中的特定函数
- Agent 需要更新配置文件中的某个值
- Agent 需要替换文档中的某段文字
- Agent 需要修正代码中的 bug

**工具行为**:
1. 验证参数（file_path, old_string, new_string, replace_all）
2. 读取文件当前内容
3. 检查 `old_string` 是否存在以及是否重复
4. 如果重复且 `replace_all=false`，返回错误提示
5. 执行字符串替换
6. 写入更新后的内容
7. 返回操作结果

**设计原则**:
- **精确匹配**: `old_string` 必须精确匹配，不支持正则表达式
- **显式确认**: 重复内容需要显式设置 `replace_all=true`
- **原子操作**: 读取-修改-写入作为原子操作执行

## 参数定义

### EditFileParamDefine

```python
class EditFileParamDefine(BaseModel):
    file_path: str = Field(
        description="要编辑的文件路径。相对于用户工作目录的路径。"
    )
    old_string: str = Field(
        description="要替换的字符串。必须精确匹配，不支持正则表达式。"
    )
    new_string: str = Field(
        description="替换后的字符串。"
    )
    replace_all: bool = Field(
        default=False,
        description=(
            "是否替换所有匹配项。如果为 False，且 old_string 在文件中出现多次，"
            "则返回错误要求用户确认。如果为 True，替换所有匹配项。"
        )
    )

    model_config = ConfigDict(extra='allow')
```

### 参数说明

| 参数 | 类型 | 默认值 | 必需 | 描述 |
|------|------|--------|------|------|
| `file_path` | `str` | - | 是 | 要编辑的文件路径 |
| `old_string` | `str` | - | 是 | 要替换的字符串（精确匹配） |
| `new_string` | `str` | - | 是 | 替换后的字符串 |
| `replace_all` | `bool` | `False` | 否 | 是否替换所有匹配项 |

### 参数验证规则

1. **file_path**:
   - 不能为空字符串
   - 必须是有效的文件路径格式
   - 对于 UserSpaceFileBackend，不能包含隐藏组件

2. **old_string**:
   - 不能为空字符串
   - 必须在文件中存在，否则返回错误

3. **new_string**:
   - 可以为空字符串（表示删除匹配内容）

4. **replace_all**:
   - 布尔值，默认 false
   - 当 `old_string` 重复出现时强制用户显式设置

## 存储后端接口需求

### 抽象接口方法

存储后端必须实现以下方法：

```python
class FileOperationsStorageBackend(ABC):
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
            - success: 是否成功执行替换
            - replace_count: 实际替换的次数
            - updated_content: 更新后的文件内容

        Raises:
            FileNotFoundError: 文件不存在
            PermissionError: 无权限访问文件
            ValueError: 路径包含隐藏组件或 old_string 为空
            DuplicateMatchError: old_string 重复出现且 replace_all=False
        """
        ...
```

### 返回值说明

返回三元组 `(success, replace_count, updated_content)`：

- **success**: 是否成功执行替换
- **replace_count**: 实际替换的次数
- **updated_content**: 更新后的完整文件内容

### 存储后端实现要点

#### MemoryFileBackend

- 从内存字典获取文件内容
- 执行字符串替换（单次或全局）
- 更新内存中的内容
- 确保操作原子性（使用锁）

#### LocalFileBackend

- 使用 `aiofiles` 异步读取文件
- 执行字符串替换
- 原子性写入更新后的内容
- 处理文件不存在错误

#### UserSpaceFileBackend

- 使用 `open_file()` 以 `r+` 模式打开文件
- 自动处理分布式锁
- 检查隐藏文件路径
- 读取、修改、写回内容

## 重复内容检测逻辑

### 检测目的

防止意外替换：当 `old_string` 在文件中多次出现时，如果不显式设置 `replace_all=true`，可能造成意外的批量替换。

### 检测算法

```python
def count_matches(content: str, old_string: str) -> int:
    """计算 old_string 在 content 中出现的次数"""
    count = 0
    start = 0
    while True:
        start = content.find(old_string, start)
        if start == -1:
            break
        count += 1
        start += len(old_string)
    return count
```

### 处理流程

```
1. 读取文件内容
2. 计算 old_string 出现次数
3. 根据次数和 replace_all 参数处理：
   - 次数 = 0: 返回错误 "未找到要替换的内容"
   - 次数 = 1: 执行替换
   - 次数 > 1 且 replace_all = False: 返回错误 "内容重复，请设置 replace_all=true"
   - 次数 > 1 且 replace_all = True: 执行全局替换
4. 执行替换操作
5. 写入更新后的内容
6. 返回结果
```

### 重复检测错误消息

当检测到重复内容时，返回清晰的消息：

```
编辑文件失败：old_string 在文件中出现多次（共3次）。

如果要替换所有匹配项，请设置 replace_all=true。

匹配位置预览：
第1处：第10行
第2处：第25行
第3处：第42行
```

### 显示匹配位置

为了帮助用户确认，可以显示匹配位置：

```python
def find_match_positions(content: str, old_string: str) -> list[int]:
    """查找所有匹配位置的行号"""
    lines = content.split('\n')
    positions = []
    for i, line in enumerate(lines, 1):
        if old_string in line:
            positions.append(i)
    return positions
```

## 错误处理

### 参数验证错误

| 错误 | 消息 | 处理 |
|------|------|------|
| `file_path` 为空 | "file_path 不能为空" | 返回 `occur_error=True` |
| `old_string` 为空 | "old_string 不能为空" | 返回 `occur_error=True` |
| 路径包含隐藏组件 | "路径包含隐藏组件，不允许访问" | 返回 `occur_error=True` |

### 内容验证错误

| 错误 | 消息 | 处理 |
|------|------|------|
| `old_string` 不存在 | "未找到要替换的内容：{old_string}" | 返回 `occur_error=True` |
| `old_string` 重复且 `replace_all=false` | "内容重复出现{count}次，请设置 replace_all=true" | 返回 `occur_error=True` |

### 存储后端错误

| 错误 | 消息 | 处理 |
|------|------|------|
| `FileNotFoundError` | "文件 '{file_path}' 不存在" | 返回 `occur_error=True` |
| `PermissionError` | "无权限编辑文件 '{file_path}'" | 返回 `occur_error=True` |
| `IsADirectoryError` | "'{file_path}' 是一个目录，不是文件" | 返回 `occur_error=True` |
| 其他异常 | "编辑文件时发生错误：{error}" | 返回 `occur_error=True` |

### 成功返回格式

```python
return ToolTaskResult(
    str_content=f"成功编辑文件：{file_path}\n替换了 {replace_count} 处内容",
    occur_error=False,
)
```

### 错误返回格式

```python
return ToolTaskResult(
    str_content=f"编辑文件失败：{error_message}",
    occur_error=True,
)
```

## 使用示例

### 示例 1：单次替换（内容唯一）

```python
# 调用
result = await edit_file_tool(
    file_path="src/main.py",
    old_string='def hello_world():',
    new_string='def hello_universe():'
)

# 输出
"""
成功编辑文件：src/main.py
替换了 1 处内容
"""
```

### 示例 2：全局替换

```python
# 调用
result = await edit_file_tool(
    file_path="src/config.py",
    old_string='"localhost"',
    new_string='"127.0.0.1"',
    replace_all=True
)

# 输出
"""
成功编辑文件：src/config.py
替换了 5 处内容
"""
```

### 示例 3：重复内容检测（错误）

```python
# 调用
result = await edit_file_tool(
    file_path="src/utils.py",
    old_string='print("debug")',
    new_string='# print("debug")',
    replace_all=False  # 未设置 replace_all
)

# 输出
"""
编辑文件失败：old_string 在文件中出现多次（共3次）。

如果要替换所有匹配项，请设置 replace_all=true。

匹配位置预览：
第1处：第15行
第2处：第28行
第3处：第43行
"""
```

### 示例 4：删除内容

```python
# 调用
result = await edit_file_tool(
    file_path="src/legacy.py",
    old_string='# TODO: remove this\n',
    new_string=''  # 空字符串表示删除
)

# 输出
"""
成功编辑文件：src/legacy.py
替换了 1 处内容
"""
```

更多示例请参考：[design_docs/examples/edit_file_example.py](examples/edit_file_example.py)
