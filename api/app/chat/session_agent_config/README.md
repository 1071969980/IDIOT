# Session Agent Config

会话代理配置管理模块，提供基于命令模式的配置操作 API。  Session Agent Config 数据模型定义于 api/agent/session_agent_config

## 目录结构

```
session_agent_config/
├── command/                    # 命令实现目录
│   ├── my_command              # 命令具体实现
│   ├── base.py                 # 命令抽象基类
│   └── registry.py             # 命令动态注册器
├── data_model.py               # API 数据模型
├── endpoints.py                # FastAPI 端点
├── router_declare.py           # 路由声明
└── README.md                   # 本文件
```

## 核心概念

### 命令模式

本模块使用命令模式封装配置操作。每个命令都包含：

- **execute()**: 执行命令的主要逻辑
- **rollback()**: 可选的回滚逻辑，在 execute() 抛出异常时自动调用

### 自动回滚机制

当命令执行失败时，系统会自动尝试调用 `rollback()` 方法恢复状态。回滚失败不会影响主流程，仅记录日志。

## API 端点

### POST /session_agent_config/command

执行配置命令。

**请求体:**
```json
{
  "command_name": "get_config",
  "params": {
    "session_id": "uuid-string",
    "config_key": "optional-key"
  }
}
```

**响应:**
```json
{
  "success": true,
  "data": { ... },
  "error_message": null,
  "command_name": "get_config",
  "rollback_performed": false
}
```

## 可用命令

**暂无**

## 开发指南

### 添加新命令

1. 在 `command/` 下创建新目录，例如 `my_command/`

2. 创建 `data_model.py` 定义输入输出模型：
```python
from pydantic import BaseModel

class MyCommandInput(BaseModel):
    session_id: str
    # 其他字段...

class MyCommandOutput(BaseModel):
    success: bool
    # 其他字段...
```

3. 创建 `command.py` 实现命令：
```python
from .data_model import MyCommandInput, MyCommandOutput
from ..base import AbstractCommand

class MyCommandCommand(AbstractCommand[MyCommandInput, MyCommandOutput]):
    async def execute(self) -> MyCommandOutput:
        # 实现命令逻辑
        pass

    async def rollback(self) -> MyCommandOutput:
        # 可选：实现回滚逻辑
        pass
```

4. 创建 `__init__.py` 按约定导出：
```python
from .command import MyCommandCommand as Command
from .data_model import MyCommandInput as Input, MyCommandOutput as Output
```

命令会被 `registry.py` 自动发现并注册，无需手动添加。

### 命令注册约定

每个命令包的 `__init__.py` 必须导出以下三个符号：

- `Command`: 命令类（继承自 `AbstractCommand`）
- `Input`: 输入模型（Pydantic BaseModel）
- `Output`: 输出模型（Pydantic BaseModel）
