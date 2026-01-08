---
文档标题：开发上下文 - 项目架构与工具规范
文档描述：描述 TODO Agent 工具的开发上下文、项目架构和工具开发规范,为后续设计和实现文档提供必要的背景知识。
文档编辑规范:
- 每个文档应该控制在300到400行,如果超过400行,请考虑拆分当前文档为同名文件夹下的多个文档,以章节名为文件名。超过50行的代码示例,请拆分成单独的文件至同名文件夹,用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关,积极编写链接和引用。链接和引用本次开发开发文档之外的文件时,尽量使用相对于项目根目录的相对路径
---

**目录**:
- [项目概述](#项目概述)
- [Agent 工具架构](#agent-工具架构)
- [工具开发规范](#工具开发规范)
- [配置模式（Config Pattern）](#配置模式config-pattern)
- [协议类模式（Protocol Pattern）](#协议类模式protocol-pattern)

## 项目概述

IDIOT (Intelligent Development Integrated & Operations Toolkit) 是一个基于 Python 的 AI 应用程序后端工具包。本项目采用"文档即软件"的开发范式，通过编写精确的自然语言规范文档来指导软件实现。

本次开发的目标是实现一个 **TODO Agent 工具系列**，专注于 **todo_write** 工具的开发。该工具用于 LLM 多轮会话中的内部状态管理，帮助 Agent 在对话过程中跟踪和管理任务。

## Agent 工具架构

### 工具在 Agent 系统中的位置

在 IDIOT 项目中，Agent 工具是 Agent 执行任务时可调用的功能单元。工具系统的核心组件包括：

1. **工具类（Tool Class）**：实际执行工具功能的类，实现 `async def __call__(**kwargs) -> ToolTaskResult` 方法
2. **工具配置（Tool Config）**：控制工具行为的配置类，继承自 `SessionToolConfigBase`
3. **工具参数（Tool Parameters）**：LLM 调用工具时传递的参数定义，使用 Pydantic BaseModel
4. **工具工厂（ToolFactory）**：负责创建和初始化工具实例的工厂类
5. **工具构造器（Tool Constructor）**：工具的构造函数，负责组装工具实例和其依赖

### 工具的核心接口

所有工具必须实现以下接口：

```python
class YourTool(object):
    def __init__(self, config: YourToolConfig, ...dependencies):
        """初始化工具，接收配置和依赖"""
        self.config = config
        # ... 其他初始化逻辑

    async def __call__(self, **kwargs: dict[str, Any]) -> ToolTaskResult:
        """
        工具的调用接口
        - 参数验证
        - 执行业务逻辑
        - 返回 ToolTaskResult
        """
        pass
```

**文件位置参考**：
- 工具基础定义：`/home/gmh/桌面/IDIOT/api/agent/tools/config_data_model.py`
- 工具数据模型：`/home/gmh/桌面/IDIOT/api/agent/tools/data_model.py`
- 工具类型定义：`/home/gmh/桌面/IDIOT/api/agent/tools/type.py`

## 工具开发规范

项目提供了详细的工具开发文档：**[`docs/for_LLM_dev/实现新的Agent工具.md`](../../../../for_LLM_dev/实现新的Agent工具.md)**

### 标准开发流程

1. **定义配置类**：继承 `SessionToolConfigBase`
2. **定义参数类**：使用 Pydantic BaseModel，启用 `extra='allow'`
3. **实现工具类**：实现 `__init__` 和 `__call__` 方法
4. **实现构造器函数**：返回 `(GENERATION_TOOL_PARAM, tool_closure)`
5. **注册工具**：在 `tool_init_function.py` 中注册 CONSTRUCTOR

### 工具目录结构示例

```
api/agent/tools/your_tool/
├── __init__.py
├── config_data_model.py      # 配置和参数定义
└── constructor.py            # 工具实现和构造器
```

**参考示例**：
- 简单工具：`/home/gmh/桌面/IDIOT/api/agent/tools/ask_user/`
- 复杂工具（含数据库）：`/home/gmh/桌面/IDIOT/api/agent/tools/a2a_chat_task/`

## 配置模式（Config Pattern）

### SessionToolConfigBase 基类

所有工具配置必须继承自 `SessionToolConfigBase`：

```python
# 文件：api/agent/tools/config_data_model.py
class SessionToolConfigBase(BaseModel):
    """工具配置的基类"""
    enabled: bool
```

**文件位置**：`/home/gmh/桌面/IDIOT/api/agent/tools/config_data_model.py:80-82`

### 扩展配置类

工具可以扩展配置类来控制不同的行为模式：

```python
from typing import Literal
from pydantic import BaseModel, Field

class YourToolConfig(SessionToolConfigBase):
    enabled: bool = True

    # 控制存储后端类型
    storage_backend: Literal["type_a", "type_b", "kwargs_DI"] = "type_a"

    # 其他配置字段
    custom_field: str | None = None
```

### 配置的默认值设置

```python
DEFAULT_TOOL_CONFIG = {
    TOOL_NAME: YourToolConfig(
        enabled=True,
        storage_backend="type_a"  # 默认值
    )
}
```

### 会话级配置聚合

工具配置在会话级别进行聚合管理：

**文件位置**：`/home/gmh/桌面/IDIOT/api/agent/session_agent_config/config_data_model.py`

```python
DEFAULT_TOOLS_CONFIG: dict[str, SessionToolConfigBase] = {
    **ASK_USER_DEFAULT_CONFIG,
    # 添加更多工具配置
}

class SessionAgentConfig(BaseModel):
    version: str
    tools_config: dict[str, SessionToolConfigBase] = DEFAULT_TOOLS_CONFIG
```

## 协议类模式（Protocol Pattern）

项目使用传统的抽象基类（ABC）模式，而非 `typing.Protocol`。

### ABC 模式示例

项目中多个关键系统使用 ABC 定义协议：

#### 1. 用户数据库抽象

**文件位置**：`/home/gmh/桌面/IDIOT/api/authentication/user_db_base.py`

```python
from abc import ABC, abstractmethod

class UserDBBase(ABC):
    @abstractmethod
    async def create_user(self, username: str, password: str, *args, **kwargs) -> str:
        pass

    @abstractmethod
    async def get_user_by_username(self, username: str) -> Optional[_User]:
        pass
```

#### 2. 向量数据库抽象

**文件位置**：`/home/gmh/桌面/IDIOT/api/vector_db/vector_db_base.py`

```python
class BaseVectorDB(ABC, Generic[VDBObjectType]):
    @abstractmethod
    def add_object(self, obj: VDBObjectType, **kwargs: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def search_by_vector(self, query_vector: list[float] | dict[str, list[float]], **kwargs: dict[str, Any]) -> list[VDBObjectType]:
        raise NotImplementedError
```

#### 3. 负载均衡策略

**文件位置**：`/home/gmh/桌面/IDIOT/api/load_balance/load_balance_strategy.py`

```python
class LoadBalanceStrategy(ABC):
    @abstractmethod
    def select_instance(self, instances: List[ServiceInstanceBase]) -> ServiceInstanceBase:
        pass

class RandomStrategy(LoadBalanceStrategy):
    def select_instance(self, instances: List[ServiceInstanceBase]) -> ServiceInstanceBase:
        return random.choice(instances)
```

### ABC 模式的关键特征

1. **使用 `abc.ABC` 和 `@abstractmethod` 装饰器**
2. **子类必须实现所有抽象方法**
3. **提供清晰的接口契约**
4. **支持多态和依赖注入**

---

**下一步**：请参考 [`02_storage_and_injection.md`](./02_storage_and_injection.md) 了解 Session Storage 机制和依赖注入流程。
