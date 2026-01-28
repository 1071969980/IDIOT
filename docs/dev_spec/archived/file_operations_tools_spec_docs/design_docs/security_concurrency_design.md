---
文档标题：security_concurrency_design
文档描述：文件操作工具的安全限制（隐藏文件检测、路径验证）和并发安全设计（分布式锁使用）。
文档编辑规范:
- 每个文档应该控制在300到400行，如果超过400行，请考虑拆分当前文档为同名文件夹下的多个文档，以章节名为文件名。超过50行的代码示例，请拆分成单独的文件至同名文件夹，用相对链接的形式引用。
- 目录最多添加两级目录。
- 如果文档内容与其他规范文档或项目文件相关，积极编写链接和引用。链接和引用本次开发文档之外的文件时，尽量使用相对于项目根目录的相对路径
---

**目录**:
- [安全与并发概述](#安全与并发概述)
- [路径验证](#路径验证)
- [隐藏文件检测](#隐藏文件检测)
- [并发安全设计](#并发安全设计)
- [分布式锁使用](#分布式锁使用)
- [安全最佳实践](#安全最佳实践)

---

## 安全与并发概述

### 安全目标

文件操作工具的安全设计旨在防止：

1. **未授权访问**: 阻止访问隐藏文件和系统敏感文件
2. **路径遍历攻击**: 防止 `../` 等路径遍历
3. **数据泄露**: 限制在用户空间范围内操作
4. **竞态条件**: 通过并发控制防止数据损坏

### 并发目标

并发设计旨在确保：

1. **数据一致性**: 多个操作不会相互干扰
2. **原子性**: 复杂操作作为原子操作执行
3. **可扩展性**: 支持分布式环境下的并发访问

### 安全模型分层

```
┌─────────────────────────────────────────────────┐
│          应用层（工具参数验证）                  │
│  - Pydantic 参数验证                             │
│  - 业务规则检查                                  │
└─────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────┐
│          存储后端层（安全策略）                  │
│  - 路径验证                                      │
│  - 隐藏文件检测                                  │
│  - 权限检查                                      │
└─────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────┐
│          基础设施层（系统安全）                  │
│  - 用户空间文件系统隔离                          │
│  - 分布式锁                                      │
│  - 文件系统权限                                  │
└─────────────────────────────────────────────────┘
```

## 路径验证

### 验证目标

防止恶意路径和非法访问：

1. **路径格式验证**: 确保路径格式合法
2. **路径遍历防护**: 阻止 `../` 等遍历攻击
3. **路径范围限制**: 限制在允许的目录范围内

### 验证实现

#### 使用 pathvalidate 库

```python
from pathvalidate import validate_filepath
from pathlib import Path

def validate_path_format(file_path: str) -> None:
    """
    验证路径格式是否合法。

    Raises:
        ValueError: 路径格式非法
    """
    try:
        validate_filepath(file_path)
    except ValidationError as e:
        raise ValueError(f"路径格式非法：{file_path}，{str(e)}")
```

#### 路径遍历检测

```python
def detect_path_traversal(file_path: str, base_path: Path) -> None:
    """
    检测路径遍历攻击。

    Args:
        file_path: 用户提供的路径
        base_path: 允许的基础路径

    Raises:
        ValueError: 检测到路径遍历攻击
    """
    resolved = Path(file_path).resolve()

    # 检查解析后的路径是否在基础路径下
    try:
        resolved.relative_to(base_path.resolve())
    except ValueError:
        raise ValueError(
            f"路径遍历攻击检测：{file_path} 超出允许范围 {base_path}"
        )
```

#### 路径验证流程

```
1. 格式验证（pathvalidate）
    │
    ├─ 通过 ▼
    │
2. 解析路径（resolve）
    │
    ├─ 通过 ▼
    │
3. 范围检查（relative_to）
    │
    ├─ 通过 ▼
    │
4. 隐藏文件检测（见下一节）
```

### 各后端的路径验证

#### MemoryFileBackend

内存后端相对宽松，但仍需要基本格式验证：

```python
async def _validate_path(self, file_path: str) -> None:
    """验证路径（内存后端）"""
    # 基本格式验证
    validate_path_format(file_path)

    # 内存后端不强制隐藏文件限制（测试环境）
    # 但建议在工具层进行检查
```

#### LocalFileBackend

本地文件后端需要严格的路径验证：

```python
async def _validate_path(self, file_path: str) -> None:
    """验证路径（本地文件后端）"""
    # 格式验证
    validate_path_format(file_path)

    # 解析完整路径
    full_path = self.base_path / file_path
    full_resolved = full_path.resolve()

    # 范围检查
    try:
        full_resolved.relative_to(self.base_path.resolve())
    except ValueError:
        raise ValueError(
            f"路径超出允许范围：{file_path}"
        )
```

#### UserSpaceFileBackend

用户空间文件系统自带路径处理：

```python
async def _validate_path(self, file_path: str) -> Path:
    """验证路径（用户空间文件系统）"""
    # 使用文件系统的路径工具
    from api.user_space.file_system.path_utils import (
        build_full_path,
        validate_path
    )

    # 基本验证
    validate_path(Path(file_path))

    # 构建完整路径
    full_path = build_full_path(self.user_id, Path(file_path))

    # 隐藏文件检测
    if _path_contains_hidden_component(full_path, Path(f"/{self.user_id}")):
        raise ValueError(
            f"路径包含隐藏组件，不允许访问：{file_path}"
        )

    return full_path
```

## 隐藏文件检测

### 定义

**隐藏文件**: 路径中任何以点（`.`）开头的组件。

### 检测规则

#### Unix 风格隐藏文件

```
.git                    ← 隐藏（直接以点开头）
.ssh/config             ← 隐藏（第一组件隐藏）
docs/.draft/article.md  ← 隐藏（中间组件隐藏）
normal/file.txt         ← 非隐藏
```

#### 检测算法

使用用户空间文件系统的检测函数：

```python
from api.user_space.file_system.fs_utils.list import _path_contains_hidden_component

def _path_contains_hidden_component(file_path: Path, base_path: Path) -> bool:
    """
    检查路径中是否包含隐藏组件（包括隐藏文件夹内的文件）。

    Args:
        file_path: 要检查的文件路径
        base_path: 用户基础路径

    Returns:
        True 如果路径包含任何隐藏组件
    """
    try:
        relative_path = file_path.relative_to(base_path)
        # 检查相对路径的每个组件
        return any(
            component.startswith(".")
            for component in relative_path.parts
        )
    except ValueError:
        # 如果无法计算相对路径，检查完整路径
        return any(
            component.startswith(".")
            for component in file_path.parts
        )
```

### 各后端的隐藏文件策略

| 后端 | 强制隐藏文件限制 | 理由 |
|------|----------------|------|
| MemoryFileBackend | 否 | 测试环境，需要灵活性 |
| LocalFileBackend | 否 | 本地测试，由用户控制 |
| UserSpaceFileBackend | **是** | 生产环境，安全要求 |

### 实现示例

#### UserSpaceFileBackend 实现

```python
class UserSpaceFileBackend(FileOperationsStorageBackend):
    def __init__(self, session_id: UUID, user_id: UUID):
        super().__init__(session_id, user_id)
        self.user_base_path = Path(f"/{user_id}")

    def _check_hidden_component(self, file_path: str) -> None:
        """检查路径是否包含隐藏组件"""
        # 构建完整路径
        from api.user_space.file_system.path_utils import build_full_path
        full_path = build_full_path(self.user_id, Path(file_path))

        # 检查隐藏组件
        if _path_contains_hidden_component(full_path, self.user_base_path):
            raise ValueError(
                f"路径包含隐藏组件，不允许访问：{file_path}"
            )

    async def read_file(self, file_path: str, **kwargs) -> tuple:
        # 在操作前检查
        self._check_hidden_component(file_path)
        # ... 继续操作
```

#### 工具层检查（可选）

```python
class ReadFileTool:
    def __init__(self, config, storage_backend):
        self.config = config
        self.storage_backend = storage_backend

        # 如果是 UserSpaceFileBackend，可以额外在工具层检查
        self._enforce_hidden_check = isinstance(
            storage_backend,
            UserSpaceFileBackend
        )

    async def __call__(self, **kwargs):
        param = ReadFileParamDefine.model_validate(kwargs)

        # 预检查（双重保护）
        if self._enforce_hidden_check:
            try:
                self.storage_backend._check_hidden_component(
                    param.file_path
                )
            except ValueError as e:
                return ToolTaskResult(
                    str_content=f"路径检查失败：{str(e)}",
                    occur_error=True
                )

        # 继续执行
        return await self._read(param)
```

## 并发安全设计

### 并发场景

文件操作工具可能面临以下并发场景：

1. **同时读取**: 多个 Agent 同时读取同一文件
2. **同时写入**: 多个 Agent 同时写入同一文件
3. **读写混合**: 一个 Agent 读取时另一个 Agent 写入
4. **编辑冲突**: 多个 Agent 同时编辑同一文件的不同位置

### 并发控制策略

#### MemoryFileBackend

使用 `asyncio.Lock` 保护内存字典：

```python
class MemoryFileBackend(FileOperationsStorageBackend):
    _memory_store: Dict[str, Dict[str, str]] = {}
    _lock: Lock = Lock()

    async def read_file(self, file_path: str, **kwargs) -> tuple:
        async with self._lock:  # 读操作也需要锁（防止写入时的不一致）
            store = self._get_session_store()
            if file_path not in store:
                raise FileNotFoundError(...)
            # ... 读取操作

    async def write_file(self, file_path: str, content: str, **kwargs) -> bool:
        async with self._lock:  # 写操作加锁
            store = self._get_session_store()
            store[file_path] = content
            return True
```

#### LocalFileBackend

使用文件锁或操作系统的原子操作：

```python
import fcntl
import asyncio

class LocalFileBackend(FileOperationsStorageBackend):
    _file_locks: Dict[str, Lock] = {}
    _locks_lock = Lock()

    async def _get_file_lock(self, file_path: str) -> Lock:
        """获取文件级别的锁"""
        async with self._locks_lock:
            if file_path not in self._file_locks:
                self._file_locks[file_path] = Lock()
            return self._file_locks[file_path]

    async def write_file(self, file_path: str, content: str, **kwargs) -> bool:
        full_path = self._resolve_path(file_path)
        file_lock = await self._get_file_lock(file_path)

        async with file_lock:  # 文件级别锁
            # 原子写入（见存储后端设计文档）
            await self._atomic_write(full_path, content)
            return True
```

#### UserSpaceFileBackend

`HybridFileObject` 内置分布式锁：

```python
class UserSpaceFileBackend(FileOperationsStorageBackend):
    async def read_file(self, file_path: str, **kwargs) -> tuple:
        full_path = self._resolve_path(file_path)

        # HybridFileObject 自动处理分布式锁
        async with open_file(self.user_id, full_path, "r") as f:
            content = f.read().decode('utf-8')
            # ... 处理内容

        # 离开上下文时自动释放锁
```

### 编辑操作的原子性

`edit_file` 是一个读-改-写操作，需要原子性保证：

```python
async def edit_file(
    self,
    file_path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False
) -> tuple:
    # 整个操作在锁的保护下
    async with await self._get_lock(file_path):
        # 1. 读取
        content = await self._read_content(file_path)

        # 2. 修改
        updated_content = self._replace(content, old_string, new_string, replace_all)

        # 3. 写回
        await self._write_content(file_path, updated_content)

        return (True, count, updated_content)
```

## 分布式锁使用

### RedisDistributedLock

用户空间文件系统使用 `RedisDistributedLock` 实现分布式锁：

**位置**: [`api/redis/distributed_lock.py`](../../../api/redis/distributed_lock.py)

**特性**：
- 基于 Redis SET NX EX 命令
- 自动续期（看门狗模式）
- 锁超时自动释放
- 可重入锁

### HybridFileObject 的锁集成

`HybridFileObject` 在文件操作时自动获取和释放锁：

```python
class HybridFileObject:
    def __init__(self, user_id, file_path, mode):
        self.user_id = user_id
        self.file_path = file_path
        self.mode = mode
        self._s3_key = build_s3_key(user_id, file_path)
        self._lock = RedisDistributedLock(f"HybridFileObject:{self._s3_key}")

    async def __aenter__(self):
        # 获取分布式锁
        if not await self._lock.acquire():
            raise LockAcquisitionError(
                f"Failed to acquire lock for file: {self.file_path}"
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # 释放分布式锁
        await self._lock.release()
```

### 锁的粒度

不同存储后端使用不同的锁粒度：

| 后端 | 锁粒度 | 实现 |
|------|--------|------|
| MemoryFileBackend | 全局锁 | `asyncio.Lock` 保护整个内存字典 |
| LocalFileBackend | 文件锁 | 每个文件一个 `asyncio.Lock` |
| UserSpaceFileBackend | 文件锁 | 每个文件一个 `RedisDistributedLock` |

### 锁超时和重试

```python
from asyncio import sleep

async def read_with_retry(
    backend: FileOperationsStorageBackend,
    file_path: str,
    max_retries: int = 3,
    retry_delay: float = 0.1
) -> tuple:
    """带重试的读取操作"""
    for attempt in range(max_retries):
        try:
            return await backend.read_file(file_path)
        except LockAcquisitionError as e:
            if attempt == max_retries - 1:
                raise
            await sleep(retry_delay * (2 ** attempt))  # 指数退避
```

## 安全最佳实践

### 1. 深度防御

在多个层次实施安全检查：

```python
# 工具层
async def __call__(self, **kwargs):
    param = ReadFileParamDefine.model_validate(kwargs)  # 第1层：参数验证
    # ... 继续传递到存储后端

# 存储后端层
async def read_file(self, file_path: str, **kwargs):
    self._validate_path(file_path)  # 第2层：路径验证
    self._check_hidden(file_path)   # 第3层：隐藏文件检查
    # ... 继续操作
```

### 2. 最小权限原则

- MemoryFileBackend: 仅在内存中操作
- LocalFileBackend: 限制在 `base_path` 下
- UserSpaceFileBackend: 限制在用户空间（`/{user_id}`）

### 3. 审计日志

```python
import logging

logger = logging.getLogger(__name__)

async def read_file(self, file_path: str, **kwargs):
    logger.info(
        f"read_file called: session={self.session_id}, "
        f"path={file_path}, backend={self.__class__.__name__}"
    )
    # ... 操作
    logger.info(f"read_file success: {file_path}")
```

### 4. 错误消息安全

不泄露敏感信息：

```python
# 不好的做法
raise ValueError(f"文件不存在：/home/user/.ssh/id_rsa")

# 好的做法
raise ValueError("文件不存在或无权限访问")
```

### 5. 资源清理

确保锁和文件句柄正确释放：

```python
async def read_file(self, file_path: str, **kwargs):
    try:
        async with open_file(self.user_id, full_path, "r") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Read failed: {e}")
        raise  # 上下文管理器会自动释放锁
```
