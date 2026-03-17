# JuiceFS 多租户客户端工作进程池

解决 JuiceFS Python SDK 在多租户场景下的资源泄漏问题。使用任务队列模式，通过进程隔离和定期重启来控制资源使用。

## 架构特点

- **按 meta_url 哈希路由**：同一文件系统的操作集中在一个 worker，LRU 缓存更有效
- **独立任务队列**：每个 worker 有独立的任务队列，避免竞争
- **进程隔离**：Worker 运行在独立进程中，资源泄漏由进程重启控制
- **类型安全**：使用 Pydantic 模型验证输入输出

```
┌─────────────────────────────────────────────────────────────┐
│                     JuiceFSWorkerPool                       │
│                                                              │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
│  │ Queue 0 │  │ Queue 1 │  │ Queue 2 │  │ Queue 3 │        │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘        │
│       │            │            │            │              │
│       ▼            ▼            ▼            ▼              │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
│  │Worker 0 │  │Worker 1 │  │Worker 2 │  │Worker 3 │        │
│  │  LRU    │  │  LRU    │  │  LRU    │  │  LRU    │        │
│  │ Clients │  │ Clients │  │ Clients │  │ Clients │        │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘        │
│       └────────────┴────────────┴────────────┘              │
│                          │                                   │
│                          ▼                                   │
│                   ┌─────────────┐                           │
│                   │Result Queue │                           │
│                   └─────────────┘                           │
└─────────────────────────────────────────────────────────────┘
```

## 快速开始

### FastAPI 集成

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from api.juiceFS.client_worker import init_worker_pool, close_worker_pool

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_worker_pool(
        num_workers=4,
        max_tasks_per_worker=500,
        max_clients_per_worker=20,
    )
    yield
    close_worker_pool()
```

### 业务代码使用

```python
from uuid import UUID
from api.juiceFS.client_worker import get_worker_pool, Operation
from api.juiceFS.client_worker.models import ReadOutput, WriteOutput

async def read_user_file(meta_url: str, file_path: str) -> bytes:
    """读取文件"""
    pool = get_worker_pool()
    result: ReadOutput = await pool.call(meta_url, Operation.READ, file_path)
    return result.content

async def write_user_file(meta_url: str, file_path: str, data: bytes) -> int:
    """写入文件"""
    pool = get_worker_pool()
    result: WriteOutput = await pool.call(meta_url, Operation.WRITE, file_path, data)
    return result.bytes_written
```

### 批量操作

使用 `batch_call` 在单个任务中执行多个操作，减少进程间通信开销：

```python
from api.juiceFS.client_worker import get_worker_pool, Operation

async def init_user_storage(meta_url: str) -> dict:
    """批量初始化用户存储目录"""
    pool = get_worker_pool()

    result = await pool.batch_call(
        meta_url,
        operations=[
            (Operation.MKDIRS, "/data"),
            (Operation.MKDIRS, "/data/files"),
            (Operation.MKDIRS, "/data/logs"),
            (Operation.WRITE, "/data/README.txt", b"User storage initialized"),
        ],
        stop_on_error=True,  # 遇到错误时停止后续操作
    )

    return {
        "total": result.total,
        "succeeded": result.succeeded,
        "failed": result.failed,
        "results": [r.model_dump() for r in result.results],
    }
```

**批量操作特点**：
- 所有操作在同一个 worker 中顺序执行
- 支持设置 `stop_on_error` 遇错停止
- 返回每个操作的独立结果
- 不支持嵌套批量操作

### 直接使用进程池

```python
from api.juiceFS.client_worker import JuiceFSWorkerPool, Operation

pool = JuiceFSWorkerPool(num_workers=4)
try:
    pool.start()
    result = await pool.call(
        "redis://localhost:6379/0",
        Operation.READ,
        "/data/file.txt"
    )
finally:
    pool.stop()
```

## 支持的操作

| Operation | 输入参数 | 输出 | 说明 |
|-----------|----------|------|------|
| `READ` | `path: str` | `content: bytes` | 读取文件 |
| `WRITE` | `path: str, data: bytes` | `bytes_written: int` | 写入文件 |
| `EXISTS` | `path: str` | `exists: bool` | 检查路径是否存在 |
| `LISTDIR` | `path: str, detail: bool = False` | `entries: list` | 列出目录 |
| `MKDIR` | `path: str, mode: int = 0o777` | `success: bool` | 创建目录 |
| `MKDIRS` | `path: str, mode: int, exist_ok: bool` | `success: bool` | 递归创建目录 |
| `REMOVE` | `path: str` | `success: bool` | 删除文件 |
| `RMDIR` | `path: str` | `success: bool` | 删除空目录 |
| `RMR` | `path: str` | `success: bool` | 递归删除目录 |
| `CLONE` | `src: str, dst: str, preserve: bool = False` | `success: bool` | 克隆文件或目录 |
| `RENAME` | `old: str, new: str` | `success: bool` | 重命名/移动 |
| `STAT` | `path: str` | `stat_info: StatResult` | 获取文件状态 |
| `TRUNCATE` | `path: str, size: int` | `success: bool` | 截断文件 |
| `CHMOD` | `path: str, mode: int` | `success: bool` | 修改权限 |
| `GETXATTR` | `path: str, name: str` | `value: bytes` | 获取扩展属性 |
| `SETXATTR` | `path: str, name: str, value: bytes, flags: int = 0` | `success: bool` | 设置扩展属性 |
| `LISTXATTR` | `path: str` | `names: list[str]` | 列出扩展属性 |
| `REMOVEXATTR` | `path: str, name: str` | `success: bool` | 删除扩展属性 |
| `BATCH` | `operations: list, stop_on_error: bool` | `results: list, total: int, succeeded: int, failed: int` | 批量操作 |

## 异常处理

```python
from api.juiceFS.client_worker.exceptions import (
    WorkerPoolError,
    TaskTimeoutError,
    TaskExecutionError,
)

try:
    pool = get_worker_pool()
    result = await pool.call(meta_url, Operation.READ, "/path/to/file")
except WorkerPoolError:
    # 工作进程池未启动或其他池级错误
    pass
except TaskTimeoutError as e:
    # 任务超时
    print(f"Task timed out: {e}")
except TaskExecutionError as e:
    # 任务执行错误
    print(f"Task {e.task_id} failed: {e}")
```

## 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `num_workers` | 4 | 工作进程数量 |
| `max_tasks_per_worker` | 500 | 每个 worker 处理的最大任务数，超过后重启 |
| `max_clients_per_worker` | 20 | 每个 worker 缓存的最大 Client 数量 |

## 模块结构

```
client_worker/
├── __init__.py      # 公开 API 导出
├── constants.py     # 枚举和配置常量
├── exceptions.py    # 异常定义
├── models.py        # Pydantic 输入输出模型
├── pool.py          # 工作进程池实现
├── worker.py        # 工作进程实现
├── lru_cache.py     # LRU 缓存实现
└── lifespan.py      # FastAPI 生命周期管理
```

## 开发指南：添加新操作

当需要为 Worker 添加新的 JuiceFS 操作时，需按以下步骤修改：

### Step 1: 添加 Operation 枚举

在 `constants.py` 中添加新的操作枚举值：

```python
# constants.py
class Operation(str, Enum):
    # ... 现有操作 ...
    NEW_OP = "new_op"  # 新操作描述
```

### Step 2: 添加输入/输出模型

在 `models.py` 中添加对应的 Pydantic 模型：

```python
# models.py

# 输入模型（继承 OperationInput）
class NewOpInput(OperationInput):
    """新操作输入"""
    path: str
    # 其他参数...

# 输出模型（继承 OperationOutput）
class NewOpOutput(OperationOutput):
    """新操作输出"""
    success: bool
    # 其他返回字段...
```

然后在 `OPERATION_REGISTRY` 中注册：

```python
# models.py - OPERATION_REGISTRY
OPERATION_REGISTRY: dict[Operation, tuple[type[OperationInput], type[OperationOutput]]] = {
    # ... 现有注册 ...
    Operation.NEW_OP: (NewOpInput, NewOpOutput),
}
```

### Step 3: 实现 Worker 处理逻辑

在 `worker.py` 中添加操作实现：

```python
# worker.py

# 1. 在导入部分添加新模型
from api.juiceFS.client_worker.models import (
    # ... 现有导入 ...
    NewOpInput,  # 新增
)

# 2. 在 _execute_operation 方法中添加处理逻辑
def _execute_operation(self, client, operation: Operation, input_model: OperationInput) -> Any:
    # ... 现有操作 ...

    elif operation == Operation.NEW_OP:
        assert isinstance(input_model, NewOpInput)
        # 调用 JuiceFS SDK
        client.new_op(input_model.path, ...)
        return {"success": True}  # 返回字典，需匹配输出模型字段

    # ... 其他操作 ...
```

### Step 4: 添加类型重载

在 `pool.py` 中添加类型重载，让 IDE 能够正确推断返回类型：

```python
# pool.py

# 1. 在导入部分添加新输出模型
from api.juiceFS.client_worker.models import (
    # ... 现有导入 ...
    NewOpOutput,  # 新增
)

# 2. 在 JuiceFSWorkerPool 类中添加 @overload 方法
@overload
async def call(
    self,
    meta_url: str,
    operation: Literal[Operation.NEW_OP],
    *args: Any,
    timeout: float = DEFAULT_TASK_TIMEOUT,
) -> NewOpOutput: ...
```

### Step 5: 更新文档

更新本 README 的「支持的操作」表格，添加新操作的说明。

### 完整示例

以添加 `CLONE` 操作为例：

```python
# constants.py
CLONE = "clone"  # 克隆文件或目录

# models.py
class CloneInput(OperationInput):
    """克隆文件或目录"""
    src: str
    dst: str
    preserve: bool = Field(default=False, description="是否保留文件属性")

class CloneOutput(OperationOutput):
    """克隆文件或目录输出"""
    success: bool

# OPERATION_REGISTRY
Operation.CLONE: (CloneInput, CloneOutput),

# worker.py
from api.juiceFS.client_worker.models import CloneInput

elif operation == Operation.CLONE:
    assert isinstance(input_model, CloneInput)
    client.clone(input_model.src, input_model.dst, input_model.preserve)
    return {"success": True}

# pool.py
from api.juiceFS.client_worker.models import CloneOutput

@overload
async def call(
    self,
    meta_url: str,
    operation: Literal[Operation.CLONE],
    *args: Any,
    timeout: float = DEFAULT_TASK_TIMEOUT,
) -> CloneOutput: ...
```

### 注意事项

1. **命名规范**：操作名使用大写下划线命名（如 `NEW_OP`），对应 JuiceFS SDK 方法名（如 `client.new_op`）
2. **输入验证**：使用 Pydantic 模型进行参数验证，复杂验证可使用 `@field_validator`
3. **错误处理**：Worker 中直接抛出异常，由 Pool 统一捕获并转换为 `TaskExecutionError`
4. **返回格式**：`_execute_operation` 返回的字典字段名必须与输出模型匹配
5. **类型安全**：确保所有重载定义在通用实现之前