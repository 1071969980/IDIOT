# Agent 工具开发规范

本文档描述了在 IDIOT 项目中开发新的 Agent 工具时要遵循的规范和实现模式。

## 目录结构

Agent 工具的核心组件位于以下目录：

```
api/agent/
├── session_agent_config/          # 会话级 Agent 配置管理
│   ├── config_data_model.py       # 配置数据模型
│   └── migration/                 # 配置迁移逻辑
├── strategy/                      # Agent 策略层
│   ├── main_agent.py              # 主 Agent 实现
│   └── main_agent_strategy.py     # 策略实现
├── sql_stat/                      # SQL 模板系统
│   └── u2a_session_agent_config/  # 用户到Agent会话配置
│       ├── u2a_session_agent_config.sql
│       └── utils.py
└── tools/                         # 工具实现
    ├── config_data_model.py       # 工具配置基类
    ├── data_model.py              # 工具数据模型
    ├── type.py                    # 类型定义
    ├── tool_factory/              # 工具工厂
    │   ├── tool_factory.py        # 工具工厂实现
    │   └── tool_init_function.py  # 工具初始化函数注册
    └── [tool_name]/               # 具体工具目录
        ├── config_data_model.py   # 工具配置模型
        └── constructor.py         # 工具构造器
```

## 工具开发规范

### 1. 工具目录结构

每个新工具都需要在 `api/agent/tools/` 下创建独立的目录：

```
api/agent/tools/[tool_name]/
├── __init__.py                    # 包文件（可选）
├── config_data_model.py           # 工具配置和参数定义
└── constructor.py                 # 工具主实现
```

#### 1.1 多工具目录模式

对于一组密切相关的工具，可以在同一目录下创建多个子工具，每个子工具有独立的 `config_data_model.py` 和 `constructor.py`：

```
api/agent/tools/[tool_group]/
├── __init__.py                    # 包文件
├── [sub_tool_a]/
│   ├── config_data_model.py
│   └── constructor.py
├── [sub_tool_b]/
│   ├── config_data_model.py
│   └── constructor.py
└── shared_module/                 # 子工具共享的辅助模块（可选）
```

现有示例：
- `file_operations/`：包含 `read_file`、`edit_file`、`write_file`、`move_file`、`copy_file`、`delete_file`、`list_directory` 7个子工具，共享 `storage_backend/`
- `skills/`：包含 `load_skill`、`skill_advisor` 2个子工具

> **注意**：多工具目录模式下，`GENERATION_TOOL_PARAM` 应使用前缀命名（如 `READ_FILE_GENERATION_TOOL_PARAM`），避免命名冲突。

### 2. 工具配置模型 (config_data_model.py)

每个工具必须定义以下组件：

#### 2.1 工具名称常量
```python
TOOL_NAME = "your_tool_name"
```

#### 2.2 配置类
继承自 `SessionToolConfigBase`，该基类包含 `enabled: bool` 和 `explicit: bool` 两个字段：

```python
class YourToolConfig(SessionToolConfigBase):
    # 添加工具特定的配置字段
    custom_setting: str = "default_value"
```

#### 2.3 默认配置
```python
DEFAULT_TOOL_CONFIG = {
    TOOL_NAME: YourToolConfig(enabled=True, explicit=False)
}
```

#### 2.4 参数定义类
使用 Pydantic 定义工具接受的参数，使用 `Field` 提供描述：

```python
class YourToolParamDefine(BaseModel):
    param1: str = Field(description="参数1的描述")
    param2: int = Field(default=10, description="参数2的描述")

    model_config = ConfigDict(extra='allow')  # 允许额外参数
```

#### 2.5 OpenAI 工具参数
```python
from openai.types.shared_params import FunctionDefinition

GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name=TOOL_NAME,
        description="工具功能的简短描述",
        parameters=YourToolParamDefine.model_json_schema()
    )
)
```

> **命名约定**：单工具目录中使用 `GENERATION_TOOL_PARAM`；多工具目录（如 `file_operations/`、`skills/`）中使用前缀命名，如 `READ_FILE_GENERATION_TOOL_PARAM`、`LOAD_SKILL_GENERATION_TOOL_PARAM`。

### 3. 工具实现类 (constructor.py)

#### 3.1 工具类定义
```python
class YourTool(object):
    def __init__(self,
                config: YourToolConfig,
                **injected_params):
        self.config = config
        # 根据工具需要接收外部注入的参数
        # 例如：user_id, session_task_id 等
        for key, value in injected_params.items():
            setattr(self, key, value)
```

#### 3.2 异步调用方法
```python
async def __call__(self, **kwargs: dict[str, Any]) -> ToolTaskResult:
    # 1. 验证参数
    try:
        param = YourToolParamDefine.model_validate(kwargs)
    except ValidationError as e:
        error_msg = "\n".join(
            f"{'.'.join(str(l) for l in err['loc'])} - {err['msg']}"
            for err in e.errors()
        )
        return ToolTaskResult(
            str_content=f"Invalid parameters:\n{error_msg}",
            occur_error=True,
        )

    # 2. 执行工具逻辑
    # ... 工具具体实现 ...

    # 3. 返回结果
    return ToolTaskResult(
        str_content="执行结果描述",
        json_content={"key": "value"},  # 可选
        occur_error=False,
    )
```

#### 3.3 构造器函数
```python
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam

def construct_tool(
    config: YourToolConfig,
    **kwargs: dict[str, Any]
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    # 从 kwargs 中提取工具所需的外部注入参数
    # 根据工具的具体需求验证必需参数
    required_params = ["user_id"]  # 根据工具需求定义必需参数
    for param in required_params:
        if param not in kwargs:
            raise ValueError(f"{param} is required")

    # 提取工具需要的注入参数
    injected_params = {k: v for k, v in kwargs.items() if k in required_params}

    tool = YourTool(config, **injected_params)

    return (
        GENERATION_TOOL_PARAM,
        tool,
    )
```

#### 3.4 构造器注册
```python
CONSTRUCTOR = {TOOL_NAME: construct_tool}
```

### 3.5 外部参数注入说明
工具构造器通过 `**kwargs` 接收外部系统注入的业务无关参数，这种设计允许：
- **灵活传递**: 工具可以根据需要接收不同的外部参数（如 user_id、session_id 等）
- **业务解耦**: 工具实现与具体业务逻辑分离，提高可复用性
- **按需验证**: 每个工具根据自身需求验证必需的注入参数

## 需要修改的文件

### 1. 工具注册文件
**文件位置**: `api/agent/tools/tool_factory/tool_init_function.py`

在 `TOOL_INIT_FUNCTIONS` 字典中导入并注册新工具：

```python
from api.agent.tools.your_tool.constructor import CONSTRUCTOR as YOUR_TOOL_CONSTRUCTOR

TOOL_INIT_FUNCTIONS: dict[str, Callable[..., tuple[ChatCompletionToolParam, ToolClosure]]] = {
    **ASK_USER_CONSTRUCTOR,
    **YOUR_TOOL_CONSTRUCTOR  # 添加这一行
}
```

### 2. 会话配置文件
**文件位置**: `api/agent/session_agent_config/config_data_model.py`

在 `ToolConfigUnion` 类型中添加新工具的配置类，以便 Pydantic 正确序列化：

```python
from api.agent.tools.your_tool.config_data_model import YourToolConfig

# 工具配置的 Union 类型，用于 Pydantic 正确序列化子类字段
# 添加新工具时需要在此处添加对应的配置类
ToolConfigUnion = Union[
    AskUserChoiceConfig,
    TodoWriteConfig,
    YourToolConfig,  # 添加这一行
]
```

> **注意**：该文件中的 `SessionAgentConfig` 类使用 `tools_config: dict[str, ToolConfigUnion]` 存储所有工具配置，新工具的配置类必须加入 `ToolConfigUnion` 才能被正确序列化和反序列化。

## 核心类型和数据模型

### 1. ToolTaskResult
工具执行结果的标准格式：

```python
class ToolTaskResult(BaseModel):
    str_content: str                    # 文本结果
    json_content: dict | None = None    # JSON 结构化结果（可选）
    occur_error: bool = False           # 是否发生错误
    HIL_data: list[HILInterruptContent] | None = None     # 人机交互数据（可选）
    u2a_session_link_data: U2ASessionLinkData | None = None  # 用户到Agent会话链接（可选）
    a2a_session_link_data: A2ASessionLinkData | None = None  # Agent到Agent会话链接（可选）
```

### 2. 工具配置基类
```python
class SessionToolConfigBase(BaseModel):
    enabled: bool  # 工具是否启用
    explicit: bool  # 是否需要用户明确确认/显式启用
```

### 3. 工具闭包类型
```python
ToolClosure = Callable[..., Coroutine[Any, Any, ToolTaskResult]]
```

## 开发注意事项

### 1. 错误处理
- 使用 `ValidationError` 处理参数验证错误
- 返回 `ToolTaskResult(occur_error=True)` 表示执行失败
- 提供清晰的错误信息

### 2. 人机交互集成
- 需要用户交互的工具可以使用 `HIL_interrupt` 函数
- 使用 `HILInterruptContent` 和相关的 body 类型
- 在 `ToolTaskResult` 中设置 `HIL_data` 字段

### 3. 会话管理
- 工具可以创建新的会话或链接到现有会话
- 使用相应的链接数据类型 (`U2ASessionLinkData` 或 `A2ASessionLinkData`)
- 会话相关的数据存储需要使用项目的 SQL 模板系统

#### SQL 模板系统
项目使用结构化的 SQL 模板系统来管理数据库操作：
- **模板位置**: `api/agent/sql_stat/` 目录下
- **结构**: 每个数据库实体都有独立的目录，包含 `.sql` 文件和 `utils.py`
- **示例**: `u2a_session_agent_config/` 目录管理用户到Agent会话配置相关的SQL操作
- **用途**: 为需要数据持久化的工具提供统一的数据库操作接口

### 4. 异步编程
- 所有工具执行必须是异步的
- 使用 `async/await` 模式
- 数据库操作使用项目的异步 SQL 引擎

### 5. 参数处理
- 默认支持额外参数 (`model_config = ConfigDict(extra='allow')`)，使用 `param.model_extra` 获取
- 如果参数结构严格固定，可以使用 `extra='forbid'` 禁止额外参数（如 `TodoItem` 模型）
- 验证必需参数的存在性

### 6. 版本管理
- 工具配置通过 `SessionAgentConfig` 进行版本管理
- 目前版本为 "v0.1"
- 配置迁移逻辑在 `migration/` 目录中实现

## 工具工厂模式

工具通过 `ToolFactory` 类进行实例化：

```python
factory = ToolFactory(
    user_id=user_id,
    session_id=session_id,
    session_task_id=session_task_id
)

tool_param, tool_closure = await factory.prepare_tool(
    tool_name="your_tool_name",
    config=YourToolConfig(enabled=True, explicit=False)
)
```

## 最佳实践

1. **命名规范**: 工具名称使用下划线分隔的小写字母
2. **参数验证**: 使用 Pydantic 进行严格的参数验证
3. **错误信息**: 提供用户友好的错误消息
4. **文档**: 在 `Field.description` 中提供清晰的参数说明
5. **测试**: 为工具编写单元测试和集成测试
6. **日志**: 使用项目的日志系统记录关键操作
7. **资源管理**: 适当管理数据库连接和其他资源

通过遵循这些规范，可以确保新工具与现有的 Agent 系统无缝集成，并保持代码的一致性和可维护性。

## 例外：非标准工具

以下工具因架构特殊，不遵循上述标准规范：

- **`tool_discovery/`**：用于运行时动态发现可用工具，不通过工具工厂注册，没有 Config 类和 CONSTRUCTOR 字典。
- **`dynamic_tool_DI/`**：动态工具依赖注入框架，不是具体工具实现，用于在运行时创建和管理工具实例。
- **`mcp/`**：MCP (Model Context Protocol) 客户端适配器，负责与外部 MCP 服务通信，不遵循标准工具的 config/constructor 结构。

这些工具属于基础设施层组件，开发新的标准 Agent 工具时无需参考其实现模式。