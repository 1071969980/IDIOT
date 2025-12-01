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

### 2. 工具配置模型 (config_data_model.py)

每个工具必须定义以下组件：

#### 2.1 工具名称常量
```python
TOOL_NAME = "your_tool_name"
```

#### 2.2 配置类
继承自 `SessionToolConfigBase`，必须包含 `enabled: bool` 字段：

```python
class YourToolConfig(SessionToolConfigBase):
    # 添加工具特定的配置字段
    custom_setting: str = "default_value"
```

#### 2.3 默认配置
```python
DEFAULT_TOOL_CONFIG = {
    TOOL_NAME: YourToolConfig(enabled=True)
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
GENERATION_TOOL_PARAM = ChatCompletionToolParam(
    type="function",
    function=FunctionDefinition(
        name=TOOL_NAME,
        description="工具功能的简短描述",
        parameters=YourToolParamDefine.model_json_schema()
    )
)
```

### 3. 工具实现类 (constructor.py)

#### 3.1 工具类定义
```python
class YourTool(object):
    def __init__(self,
                config: YourToolConfig,
                session_task_id: UUID):
        self.config = config
        self.session_task_id = session_task_id
```

#### 3.2 异步调用方法
```python
async def __call__(self, **kwargs: dict[str, Any]) -> ToolTaskResult:
    # 1. 验证参数
    try:
        param = YourToolParamDefine.model_validate(kwargs)
    except ValidationError as e:
        error_msg = "\n".join([error["msg"] for error in e.errors()])
        return ToolTaskResult(
            str_content=f"Invalid parameters: \n" + error_msg,
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
def construct_tool(
    config: YourToolConfig,
    **kwargs: dict[str, Any]
) -> tuple[ChatCompletionToolParam, ToolClosure]:
    session_task_id: UUID | None = kwargs.get("session_task_id")
    if session_task_id is None:
        raise ValueError("session_task_id is required")

    tool = YourTool(config, session_task_id)

    return (
        GENERATION_TOOL_PARAM,
        tool,
    )
```

#### 3.4 构造器注册
```python
CONSTRUCTOR = {TOOL_NAME: construct_tool}
```

## 需要修改的文件

### 1. 工具注册文件
**文件位置**: `api/agent/tools/tool_factory/tool_init_function.py`

在 `TOOL_INIT_FUNCTIONS` 字典中导入并注册新工具：

```python
from api.agent.tools.your_tool.constructor import CONSTRUCTOR as YOUR_TOOL_CONSTRUCTOR

TOOL_INIT_FUNCTIONS: dict[str, Callable[..., tuple[ChatCompletionToolParam, ToolClosure]]] = {
    **A2A_CHAT_TASK_CONSTRUCTOR,
    **ASK_USER_CONSTRUCTOR,
    **YOUR_TOOL_CONSTRUCTOR  # 添加这一行
}
```

### 2. 会话配置文件
**文件位置**: `api/agent/session_agent_config/config_data_model.py`

在 `DEFAULT_TOOLS_CONFIG` 中添加工具的默认配置：

```python
from api.agent.tools.your_tool.config_data_model import DEFAULT_TOOL_CONFIG as YOUR_TOOL_DEFAULT_CONFIG

DEFAULT_TOOLS_CONFIG: dict[str, SessionToolConfigBase] = {
    # **A2A_CHAT_TASK_DEFAULT_CONFIG,  # 某些工具可能在默认配置中被禁用
    **ASK_USER_DEFAULT_CONFIG,
    **YOUR_TOOL_DEFAULT_CONFIG  # 添加这一行
}

```

## 核心类型和数据模型

### 1. ToolTaskResult
工具执行结果的标准格式：

```python
class ToolTaskResult(BaseModel):
    str_content: str                    # 文本结果
    json_content: dict | None = None    # JSON 结构化结果（可选）
    occur_error: bool = False           # 是否发生错误
    HIL_data: list[HILData] | None = None               # 人机交互数据（可选）
    u2a_session_link_data: U2ASessionLinkData | None = None  # 用户到Agent会话链接（可选）
    a2a_session_link_data: A2ASessionLinkData | None = None  # Agent到Agent会话链接（可选）
```

### 2. 工具配置基类
```python
class SessionToolConfigBase(BaseModel):
    enabled: bool  # 工具是否启用
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
- 支持额外参数 (`model_config = ConfigDict(extra='allow')`)
- 使用 `param.model_extra` 获取额外参数
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

tool_param, tool_closure = await factory.prerare_tool(
    tool_name="your_tool_name",
    config=YourToolConfig(enabled=True)
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