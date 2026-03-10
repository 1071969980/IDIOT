# User Pod Command 模块

用于向 Kubernetes 用户 Pod 发送 bash 命令的上下文管理器及其相关功能包。

## 概述

本模块提供了一套完整的命令执行会话管理机制，支持：

- **Pod 自动拉起**：查询容器状态，不存在时自动调用创建接口
- **心跳维护**：后台任务定期发送心跳，保持 Pod 存活
- **状态监测**：监测 Pod 运行状态，异常时触发中断信号
- **超时管理**：会话超时自动触发中断
- **命令执行**：支持普通执行和实时回调两种模式
- **中断支持**：通过 `threading.Event` 实现跨任务中断

## 依赖关系

```
┌─────────────────────────────────────────────────────────────┐
│                    api 服务 (FastAPI)                        │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              user_pod_command 模块                   │   │
│  │                                                     │   │
│  │  ┌─────────────────┐    ┌──────────────────────┐   │   │
│  │  │ context_manager │───▶│  scheduler_client    │   │   │
│  │  │ (会话管理)       │    │  (HTTP 客户端)        │   │   │
│  │  └────────┬────────┘    └──────────┬───────────┘   │   │
│  │           │                        │               │   │
│  │           ▼                        ▼               │   │
│  │  ┌─────────────────┐    ┌──────────────────────┐   │   │
│  │  │    executor     │    │ user_pod_scheduler   │   │   │
│  │  │ (命令执行)       │    │ 服务 (HTTP API)       │   │   │
│  │  └────────┬────────┘    └──────────────────────┘   │   │
│  │           │                                        │   │
│  └───────────┼────────────────────────────────────────┘   │
│              ▼                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                 Kubernetes API                       │   │
│  │              (CoreV1Api.exec)                        │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## 快速开始

### 基本用法

```python
from api.user_pod_command import pod_command_session, execute_command

async def example():
    async with pod_command_session(user_id) as session:
        # 执行命令并获取结果
        result = await execute_command(session, "ls -la /juice")
        print(f"stdout: {result.stdout}")
        print(f"stderr: {result.stderr}")
        print(f"returncode: {result.returncode}")
```

### 实时输出回调

```python
from api.user_pod_command import pod_command_session, execute_command_with_callback

async def example_stream():
    async def on_stdout(data: str):
        print(f"[OUT] {data}", end="")

    async def on_stderr(data: str):
        print(f"[ERR] {data}", end="")

    async with pod_command_session(user_id) as session:
        result = await execute_command_with_callback(
            session,
            "for i in 1 2 3; do echo step $i; sleep 1; done",
            on_stdout=on_stdout,
            on_stderr=on_stderr,
        )
```

### 命令中断

```python
import asyncio
from api.user_pod_command import pod_command_session, execute_command

async def example_interrupt():
    async with pod_command_session(user_id) as session:
        # 在另一个任务中触发中断
        async def interrupt_after(seconds: float):
            await asyncio.sleep(seconds)
            session.interrupt_event.set()

        asyncio.create_task(interrupt_after(3))

        # 执行长时间命令
        result = await execute_command(session, "sleep 100")
        print(f"Interrupted: {result.interrupted}")
```

## API 参考

### `pod_command_session()`

异步上下文管理器，管理 Pod 命令会话的生命周期。

```python
async with pod_command_session(
    user_id: UUID | str,
    heartbeat_interval: float = 30.0,      # 心跳间隔（秒）
    status_check_interval: float = 10.0,   # 状态检查间隔（秒）
    session_timeout: float = 3600.0,       # 会话超时（秒）
    pod_ready_timeout: float = 300.0,      # Pod 就绪等待超时（秒）
) -> PodCommandSession:
```

**进入上下文时：**

1. 查询容器状态，不存在则调用拉起接口
2. 等待 Pod 就绪，超时抛出 `PodCreationTimeoutError`
3. 初始化 `threading.Event` 作为中断信号
4. 启动心跳循环任务
5. 启动状态监测任务
6. 启动超时计时任务

**退出上下文时：**

1. 设置 `session.is_active = False`
2. 取消所有后台任务

### `execute_command()`

执行命令并返回所有输出。

```python
result = await execute_command(
    session: PodCommandSession,
    command: str,
    timeout: Optional[float] = None,  # 命令超时（秒）
) -> CommandResult
```

### `execute_command_with_callback()`

执行命令并通过回调实时输出。

```python
result = await execute_command_with_callback(
    session: PodCommandSession,
    command: str,
    on_stdout: Callable[[str], Awaitable[None]],
    on_stderr: Optional[Callable[[str], Awaitable[None]]] = None,
    timeout: Optional[float] = None,
) -> CommandResult
```

## 数据模型

### `CommandResult`

```python
@dataclass
class CommandResult:
    stdout: str                    # 标准输出
    stderr: str                    # 标准错误
    returncode: Optional[int]      # 退出码
    interrupted: bool = False      # 是否被中断
    error: Optional[str] = None    # 错误信息
```

### `PodCommandSession`

```python
@dataclass
class PodCommandSession:
    user_id: UUID                  # 用户ID
    pod_name: str                  # Pod 名称
    namespace: str                 # K8S 命名空间
    interrupt_event: Event         # 中断信号（多线程安全）
    is_active: bool = True         # 会话是否活跃
    last_error: Optional[str]      # 最后错误信息
```

## 异常类型

| 异常 | 说明 |
|------|------|
| `UserPodCommandError` | 基础异常 |
| `PodNotReadyError` | Pod 未就绪 |
| `PodCreationTimeoutError` | Pod 创建超时 |
| `PodStatusAbnormalError` | Pod 状态异常 |
| `SessionTimeoutError` | 会话超时 |
| `CommandExecutionError` | 命令执行错误 |
| `CommandInterruptedError` | 命令被中断 |
| `SchedulerServiceError` | 调度器服务错误 |

## 配置常量

| 常量 | 默认值 | 说明 |
|------|--------|------|
| `DEFAULT_HEARTBEAT_INTERVAL_SECONDS` | 30.0 | 心跳间隔 |
| `DEFAULT_STATUS_CHECK_INTERVAL_SECONDS` | 10.0 | 状态检查间隔 |
| `DEFAULT_SESSION_TIMEOUT_SECONDS` | 3600.0 | 会话超时（1小时） |
| `DEFAULT_POD_READY_TIMEOUT_SECONDS` | 300.0 | Pod 就绪等待超时（5分钟） |
| `COMMAND_POLL_INTERVAL_SECONDS` | 0.05 | 命令轮询间隔（50ms） |
| `INTERRUPT_SIGINT` | `b'\x03'` | Ctrl+C 中断信号 |

## 注意事项

1. **短超时轮询**：`update(timeout=0.05)` 最多阻塞 50ms，对事件循环有轻微阻塞
2. **线程安全**：`interrupt_event` 使用 `threading.Event`，可跨线程/任务安全使用
3. **心跳容错**：心跳失败时记录日志，不会中断会话
4. **服务依赖**：依赖 `user_pod_scheduler` 服务运行

## 文件结构

```
api/user_pod_command/
├── __init__.py              # 模块导出
├── constants.py             # 常量定义
├── exceptions.py            # 自定义异常
├── data_model.py            # 数据模型
├── scheduler_client.py      # HTTP 客户端
├── context_manager.py       # 上下文管理器
└── executor.py              # 命令执行器
```