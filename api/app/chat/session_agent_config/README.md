# Session Agent Config

会话代理配置管理模块，提供基于命令模式的配置操作 API。  Session Agent Config 数据模型定义于 api/agent/session_agent_config

## 目录结构

```
session_agent_config/
├── command/                    # 命令实现目录（支持嵌套子目录）
│   ├── my_command/             # 扁平命令 → key: "my_command"
│   ├── nested/
│   │   └── sub_command/        # 嵌套命令 → key: "nested.sub_command"
│   ├── base.py                 # 命令抽象基类
│   └── registry.py             # 命令动态注册器（递归发现）
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

| 命令名称 | 说明 | 写入 overlay |
|---|---|---|
| `get_tools_status` | 获取工具的 enabled 和 explicit 状态 | 否 |
| `update_tools_status` | 更新工具的 enabled/explicit 状态 | 是 |
| `get_mcp_servers_config` | 获取 MCP 服务器配置列表 | 否 |
| `update_mcp_servers_config` | 更新 MCP 服务器配置列表 | 是 |
| `test_mcp_connection` | 测试 MCP 服务器连接 | 否 |

**读取命令**支持可选的 `branch_name` 参数，用于读取 overlay 合并后的有效配置。不提供时返回基础配置。

**写入命令**需要 `branch_name` 参数，修改目标分支叶子任务的 `storage_snapshot` 中的 overlay。

## 开发指南

### 添加新命令

1. 在 `command/` 下（或任意深度的子目录中）创建新目录，例如 `my_command/`

   命令的注册 key 由目录结构决定，使用点号分隔。例如 `command/file_system/project/` 的 key 为 `file_system.project`。

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

命令会被 `registry.py` 递归自动发现并注册，无需手动添加。

### 命令注册约定

`registry.py` 递归遍历 `command/` 目录，自动发现命令包。目录本身可以只是组织用途（不导出 `Command/Input/Output`），只要其子目录中存在命令包即可。

每个命令包的 `__init__.py` 必须导出以下三个符号：

- `Command`: 命令类（继承自 `AbstractCommand`）
- `Input`: 输入模型（Pydantic BaseModel）
- `Output`: 输出模型（Pydantic BaseModel）

注册 key 规则：取相对于 `command/` 的目录路径，用点号连接。例如：
- `command/get_tools_status/` → `get_tools_status`
- `command/file_system/project/` → `file_system.project`
