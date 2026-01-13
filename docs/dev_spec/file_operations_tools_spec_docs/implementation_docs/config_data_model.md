---
文档标题：config_data_model
文档描述：配置模型实现细节，包括工具名称常量、配置类、参数定义类、OpenAI 工具参数和默认配置。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [配置模型概述](#配置模型概述)
- [工具名称常量](#工具名称常量)
- [配置类设计](#配置类设计)
- [参数定义类设计](#参数定义类设计)
- [OpenAI 工具参数](#openai-工具参数)
- [默认配置](#默认配置)

---

## 配置模型概述

### 目的

配置模型（`config_data_model.py`）定义了文件操作工具的：

1. **工具身份**: 工具名称常量
2. **配置结构**: 工具配置类
3. **参数规范**: 参数定义类（使用 Pydantic）
4. **工具描述**: OpenAI Function Calling 格式的工具参数
5. **默认配置**: 用于系统初始化的默认配置

### 设计原则

1. **遵循基类规范**: 配置类继承 `SessionToolConfigBase`
2. **类型安全**: 使用 Pydantic 进行类型验证
3. **描述完整**: 每个参数都有清晰的描述
4. **灵活扩展**: 支持额外参数（`extra='allow'`）

### 文件结构

每个工具的 `config_data_model.py` 包含：

```python
# 工具名称常量
TOOL_NAME = "tool_name"

# 配置类
class ToolConfig(SessionToolConfigBase):
    enabled: bool = True
    storage_backend: Literal["memory", "local", "user_space", "kwargs_DI"] = "memory"

# 参数定义类
class ToolParamDefine(BaseModel):
    param1: str = Field(description="...")
    param2: int | None = Field(default=None, description="...")
    model_config = ConfigDict(extra='allow')

# OpenAI 工具参数
GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name=TOOL_NAME,
        description="...",
        parameters=ToolParamDefine.model_json_schema()
    )
)

# 默认配置
DEFAULT_TOOL_CONFIG = {
    TOOL_NAME: ToolConfig(enabled=True)
}
```

## 工具名称常量

### 定义

```python
TOOL_NAME = "read_file"  # 或 "edit_file", "write_file"
```

### 用途

- 作为配置字典的键
- OpenAI Function Calling 的函数名
- 日志记录和错误消息

### 命名规范

- 使用下划线分隔的小写字母
- 与目录名保持一致
- 简洁描述工具功能

## 配置类设计

### 基类要求

所有工具配置必须继承 `SessionToolConfigBase`：

```python
from api.agent.tools.config_data_model import SessionToolConfigBase

class SessionToolConfigBase(BaseModel):
    enabled: bool  # 工具是否启用
```

### 配置类定义

三个工具使用相同的配置类设计：

```python
from pydantic import BaseModel, Field
from typing import Literal

class ReadFileConfig(SessionToolConfigBase):
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

### 配置类参数

| 参数 | 类型 | 默认值 | 必需 | 描述 |
|------|------|--------|------|------|
| `enabled` | `bool` | `True` | 是 | 工具是否启用 |
| `storage_backend` | `Literal[...]` | `"memory"` | 是 | 存储后端类型 |
| `local_base_path` | `str \| None` | `None` | 否 | 本地文件基础路径 |

## 参数定义类设计

### 通用结构

```python
from pydantic import BaseModel, Field, ConfigDict

class ToolParamDefine(BaseModel):
    """参数定义类"""

    # 参数定义
    param1: str = Field(description="参数描述")
    param2: int | None = Field(default=None, description="可选参数描述")

    # 允许额外参数
    model_config = ConfigDict(extra='allow')
```

### read_file 参数定义

```python
class ReadFileParamDefine(BaseModel):
    """read_file 工具参数定义"""

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

### edit_file 参数定义

```python
class EditFileParamDefine(BaseModel):
    """edit_file 工具参数定义"""

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

### write_file 参数定义

```python
class WriteFileParamDefine(BaseModel):
    """write_file 工具参数定义"""

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

### 参数验证规则

#### Pydantic 自动验证

```python
# 类型验证
param = ReadFileParamDefine.model_validate({
    "file_path": "test.txt",
    "offset": "invalid"  # 会抛出 ValidationError
})

# 必需字段验证
param = ReadFileParamDefine.model_validate({
    # 缺少 file_path，会抛出 ValidationError
})
```

#### 自定义验证

```python
from pydantic import field_validator

class WriteFileParamDefine(BaseModel):
    file_path: str = Field(description="...")
    content: str = Field(description="...")
    mode: Literal["create", "overwrite"] = "create"

    @field_validator('file_path')
    @classmethod
    def validate_file_path(cls, v: str) -> str:
        if not v or v.strip() == "":
            raise ValueError("file_path 不能为空")
        return v
```

## OpenAI 工具参数

### 定义格式

```python
from openai.types.shared_params import FunctionDefinition
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name=TOOL_NAME,
        description="工具功能的简短描述",
        parameters=ToolParamDefine.model_json_schema()
    )
)
```

### read_file 工具参数

```python
READ_FILE_GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name="read_file",
        description="读取文件内容，支持偏移量、行数限制和行号显示",
        parameters=ReadFileParamDefine.model_json_schema()
    )
)
```

### edit_file 工具参数

```python
EDIT_FILE_GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name="edit_file",
        description="编辑文件内容，通过替换指定的字符串实现",
        parameters=EditFileParamDefine.model_json_schema()
    )
)
```

### write_file 工具参数

```python
WRITE_FILE_GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name="write_file",
        description="向文件写入内容，支持创建新文件或覆盖现有文件",
        parameters=WriteFileParamDefine.model_json_schema()
    )
)
```

### JSON Schema 示例

`model_json_schema()` 生成的 JSON Schema：

```json
{
  "type": "object",
  "properties": {
    "file_path": {
      "type": "string",
      "description": "要读取的文件路径。相对于用户工作目录的路径。"
    },
    "offset": {
      "anyOf": [{"type": "integer"}, {"type": "null"}],
      "default": null,
      "description": "起始行的偏移量（从0开始）..."
    },
    "limit": {
      "anyOf": [{"type": "integer"}, {"type": "null"}],
      "default": null,
      "description": "要读取的最大行数..."
    },
    "show_line_numbers": {
      "type": "boolean",
      "default": false,
      "description": "是否在输出中显示行号..."
    }
  },
  "required": ["file_path"]
}
```

## 默认配置

### 定义格式

```python
DEFAULT_TOOL_CONFIG = {
    TOOL_NAME: ToolConfig(enabled=True)
}
```

### 三个工具的默认配置

```python
# read_file/config_data_model.py
DEFAULT_TOOL_CONFIG = {
    "read_file": ReadFileConfig(
        enabled=True,
        storage_backend="memory"
    )
}

# edit_file/config_data_model.py
DEFAULT_TOOL_CONFIG = {
    "edit_file": EditFileConfig(
        enabled=True,
        storage_backend="memory"
    )
}

# write_file/config_data_model.py
DEFAULT_TOOL_CONFIG = {
    "write_file": WriteFileConfig(
        enabled=True,
        storage_backend="memory"
    )
}
```

### 默认值说明

| 参数 | 默认值 | 理由 |
|------|--------|------|
| `enabled` | `True` | 工具默认启用 |
| `storage_backend` | `"memory"` | 测试环境默认，生产环境需配置 |

### 生产环境配置建议

```python
# 生产环境应在 session_agent_config 中覆盖默认配置
DEFAULT_TOOLS_CONFIG = {
    "read_file": ReadFileConfig(
        enabled=True,
        storage_backend="user_space"  # 生产环境使用用户空间文件系统
    ),
    "edit_file": EditFileConfig(
        enabled=True,
        storage_backend="user_space"
    ),
    "write_file": WriteFileConfig(
        enabled=True,
        storage_backend="user_space"
    )
}
```

### 默认配置合并

```python
from api.agent.tools.read_file.config_data_model import DEFAULT_TOOL_CONFIG as READ_FILE_DEFAULT
from api.agent.tools.edit_file.config_data_model import DEFAULT_TOOL_CONFIG as EDIT_FILE_DEFAULT
from api.agent.tools.write_file.config_data_model import DEFAULT_TOOL_CONFIG as WRITE_FILE_DEFAULT

# 合并默认配置
MERGED_DEFAULT_CONFIG = {
    **READ_FILE_DEFAULT,
    **EDIT_FILE_DEFAULT,
    **WRITE_FILE_DEFAULT
}
```

## 配置示例

### 内存存储配置

```python
config = ReadFileConfig(
    enabled=True,
    storage_backend="memory"
)
```

### 本地文件存储配置

```python
config = ReadFileConfig(
    enabled=True,
    storage_backend="local",
    local_base_path="/tmp/file_tools"
)
```

### 用户空间文件系统配置

```python
config = ReadFileConfig(
    enabled=True,
    storage_backend="user_space"
)
```

### 依赖注入配置

```python
# 创建自定义存储后端
custom_backend = CustomFileBackend(session_id=session_id)

# 使用依赖注入
config = ReadFileConfig(
    enabled=True,
    storage_backend="kwargs_DI"
)

# 构造器中注入
tool = construct_read_file(
    config=config,
    session_id=session_id,
    storage_backend=custom_backend  # 通过 kwargs 注入
)
```
