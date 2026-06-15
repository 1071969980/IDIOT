# JuiceFS Python Binding 技术分析与多租户实践指南

## 概述

本报告分析 JuiceFS Python SDK 的实现架构，重点关注多 Client 实例场景下的资源管理问题，并提供适合多租户 API 服务的解决方案。

---

## 1. 架构概览

### 1.1 技术栈

```
Python 代码 (juicefs.py)
       │
       │ ctypes (FFI)
       ▼
libjfs.so (Go c-shared library)
       │
       ▼
JuiceFS 核心引擎
   ├── meta.Meta       (元数据客户端)
   ├── chunk.ChunkStore (数据块存储)
   └── vfs.CacheFiller (缓存管理)
```

### 1.2 核心文件

| 文件 | 职责 |
|------|------|
| `sdk/python/juicefs/juicefs/juicefs.py` | Python 侧 Client 实现 |
| `sdk/python/juicefs/juicefs/libjfs.so` | Go 编译的共享库 |
| `sdk/java/libjfs/main.go` | Go 侧共享库实现 |

### 1.3 编译流程

```bash
# 第一步：编译 Go 共享库
go build -buildmode c-shared -ldflags="-s -w" \
    -o juicefs/juicefs/libjfs.so ../java/libjfs

# 第二步：构建 Python 包
cd juicefs && python3 -m build -w
```

---

## 2. Python 侧实现

### 2.1 库加载机制

Python 通过 `ctypes` 动态加载 Go 共享库：

```python
from ctypes import cdll, c_int64, c_int32

class JuiceFSLib:
    def __init__(self):
        self.lib = cdll.LoadLibrary("libjfs.so")

    def __getattr__(self, name):
        fn = getattr(self.lib, name)
        # 配置返回类型和错误检查
        if name == "jfs_init" or name == "jfs_lseek":
            fn.restype = c_int64
        elif name.startswith("jfs"):
            fn.restype = c_int32
        fn.errcheck = check_error  # 负数转 OSError
        return fn
```

### 2.2 Client 类

```python
class Client:
    def __init__(self, name, meta, **kwargs):
        # 构建配置 JSON
        config = {"meta": meta, "bucket": bucket, ...}
        jsonConf = json.dumps(config, sort_keys=True)

        # 获取用户/组信息
        user = pwd.getpwuid(os.geteuid())
        groups = [grp.getgrgid(gid).gr_name for gid in os.getgrouplist(...)]

        # 调用 Go 初始化
        self.h = self.lib.jfs_init(
            0, 0,
            name.encode(),
            jsonConf.encode(),
            user.pw_name.encode(),
            ','.join(groups).encode(),
            ...
        )

    def __del__(self):
        # 清理资源
        self.lib.jfs_term(threading.current_thread().ident, self.h)
```

**关键点**：
- `self.h` 是 Go 返回的 64 位句柄，用于后续所有操作
- 每个操作都传递线程 ID (`_tid()`) 用于并发隔离

---

## 3. Go 侧实现

### 3.1 全局状态

Go 共享库维护以下全局数据结构：

```go
var (
    // 文件描述符管理
    filesLock  sync.Mutex
    openFiles  = make(map[int32]*fwrapper)  // fd -> 文件包装器
    nextHandle = int32(1)

    // 文件系统实例管理
    fslock       sync.Mutex
    handlers     = make(map[int64]*wrapper)     // handle -> wrapper
    nextFsHandle int64 = 0

    // 复用机制：相同配置的 FileSystem 可被多个 wrapper 共享
    activefs = make(map[fsKey][]*wrapper)  // fsKey -> wrappers
)

// fsKey 用于判断是否可以复用底层 FileSystem
type fsKey struct {
    name string      // 卷名
    conf javaConf    // 配置（包含 meta URL）
}
```

### 3.2 Wrapper 结构

```go
type wrapper struct {
    *fs.FileSystem    // 嵌入的 JuiceFS 文件系统
    volname    string
    ctx        meta.Context
    m          *mapping      // 用户/组 ID 映射
    user       string
    superuser  string
    supergroup string
    conf       javaConf
}
```

### 3.3 FileSystem 结构

```go
type FileSystem struct {
    conf        *vfs.Config
    m           meta.Meta           // 元数据客户端（连接池）
    store       chunk.ChunkStore    // 数据块存储
    reader      vfs.DataReader      // 数据读取器
    writer      vfs.DataWriter      // 数据写入器
    cacheFiller *vfs.CacheFiller    // 缓存填充器

    // 内存缓存
    entries     map[Ino]map[string]*entryCache
    attrs       map[Ino]*attrCache

    // 监控
    registry    *prometheus.Registry
}
```

### 3.4 元数据客户端

FileSystem 中最关键的资源是元数据客户端：

**Redis 客户端**：
```go
type redisMeta struct {
    rdb    redis.UniversalClient  // Redis 连接池
    prefix string
    cache  *redisCache
}
```

**SQL 客户端** (MySQL/PostgreSQL)：
```go
type dbMeta struct {
    db    *xorm.Engine   // 数据库连接池
    spool *sync.Pool     // 会话池
    snap  *dbSnap        // 快照缓存
}
```

---

## 4. 核心机制分析

### 4.1 初始化流程 (jfs_init)

```go
func jfs_init(credentialPtr uintptr, count int32, cname, cjsonConf,
              cuser, group, superuser, supergroup *C.char) int64 {

    // 解析配置
    name := C.GoString(cname)
    var jConf javaConf
    json.Unmarshal([]byte(C.GoString(cjsonConf)), &jConf)

    // 调用 getOrCreate 创建或复用 FileSystem
    return getOrCreate(name, user, groups, superuser, supergroup, jConf, func() *fs.FileSystem {
        // 创建新的 FileSystem：
        // 1. 创建元数据客户端 (Redis/MySQL 连接池)
        // 2. 创建对象存储客户端
        // 3. 创建缓存管理器
        // 4. 启动后台任务
    })
}
```

### 4.2 复用机制 (getOrCreate)

```go
func getOrCreate(name, user, groups, superuser, supergroup string,
                 conf javaConf, f func() *fs.FileSystem) int64 {

    fslock.Lock()
    defer fslock.Unlock()

    // 关键：fsKey 由 name + conf 决定
    // conf 中包含 MetaURL，所以不同的元数据地址 = 不同的 key
    key := fsKey{name: name, conf: cleanConf(conf)}
    ws := activefs[key]

    var jfs *fs.FileSystem
    var m *mapping

    if len(ws) > 0 {
        // 复用已有的 FileSystem
        jfs = ws[0].FileSystem
        m = ws[0].m
    } else {
        // 创建新的 FileSystem
        jfs = f()
    }

    // 总是创建新的 wrapper 和 handle
    w := &wrapper{jfs, name, nil, m, user, superuser, supergroup, conf}
    activefs[key] = append(ws, w)
    nextFsHandle++
    handlers[nextFsHandle] = w

    return nextFsHandle
}
```

### 4.3 清理流程 (jfs_term) - 问题所在

```go
func jfs_term(pid int64, h int64) int32 {
    w := handlers[h]
    if w == nil {
        return 0
    }

    // 1. 关闭该 handle 打开的所有文件
    for fd, f := range openFiles {
        if f.w == w {
            f.Close(ctx)
            delete(openFiles, fd)
        }
    }

    // 2. 从 handlers 移除
    delete(handlers, h)

    // 3. 从 activefs 移除 wrapper
    for k, ws := range activefs {
        for i := range ws {
            if ws[i] == w {
                if len(ws) > 1 {
                    // 还有其他 wrapper 引用，只移除 wrapper
                    ws[i] = ws[len(ws)-1]
                    activefs[k] = ws[:len(ws)-1]
                } else {
                    // 关键问题：不关闭 FileSystem！
                    // "don't close the filesystem, so it can be re-used later"
                    _ = w.Flush()
                    // w.Close()  <- 注释掉了
                    // delete(activefs, k)  <- 注释掉了
                }
            }
        }
    }
    return 0
}
```

---

## 5. 多租户场景问题

### 5.1 场景描述

在多租户 API 服务中，每个用户拥有独立的元数据库：

```
用户A → Client → FileSystem A (Redis 连接池A + 缓存)
用户B → Client → FileSystem B (Redis 连接池B + 缓存)
用户C → Client → FileSystem C (Redis 连接池C + 缓存)
...
用户N → Client → FileSystem N (Redis 连接池N + 缓存)
```

### 5.2 资源泄漏

由于 `jfs_term` 不释放 FileSystem，导致：

| 资源类型 | 泄漏情况 |
|----------|----------|
| 元数据连接池 | 每个用户的连接池永不释放 |
| 内存缓存 | entries/attrs map 持续累积 |
| goroutine | 后台任务线程不停止 |
| 磁盘缓存 | 缓存目录不清理 |

### 5.3 内存增长曲线

```
内存使用
    │
    │                    ╱ 饱和或 OOM
    │                  ╱
    │               ╱
    │            ╱
    │         ╱
    │      ╱
    │   ╱  活跃用户数增长
    └──────────────────────► 时间
```

---

## 6. 解决方案：任务队列模式

### 6.1 架构设计

```
                    ┌─────────────────────┐
                    │   主进程 (API)       │
用户请求 ──────────►│   - 认证/授权        │
                    │   - 任务分发         │
                    │   - 结果聚合         │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
        ┌──────────┐    ┌──────────┐    ┌──────────┐
        │ Worker 1 │    │ Worker 2 │    │ Worker N │
        │          │    │          │    │          │
        │ LRU缓存  │    │ LRU缓存  │    │ LRU缓存  │
        │ 最多K个  │    │ 最多K个  │    │ 最多K个  │
        │ Client   │    │ Client   │    │ Client   │
        └──────────┘    └──────────┘    └──────────┘
              │
              ▼
         定期重启 (M 个任务后)
```

### 6.2 设计要点

1. **LRU 缓存**：每个 Worker 限制缓存的 Client 数量
2. **定期重启**：处理 M 个任务后重启 Worker，释放 Go 侧资源
3. **进程隔离**：Worker 崩溃不影响主进程
4. **任务队列**：`multiprocessing.Queue` 通信

### 6.3 完整实现

```python
"""
JuiceFS 多租户工作进程池

使用方法:
    pool = JuiceFSWorkerPool(num_workers=4)
    pool.start()

    # 提交任务
    task_id = pool.submit("redis://user-meta/0", "read", "/data/file.txt")
    result = pool.get_result(task_id)

    # 定期重启（可选）
    pool.restart_workers()
"""

import multiprocessing as mp
from multiprocessing import Queue
from queue import Empty
import time
import traceback
from typing import Any, Callable, Dict, Optional, Tuple
from dataclasses import dataclass
from collections import OrderedDict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Task:
    """任务定义"""
    task_id: int
    meta_url: str
    operation: str
    args: tuple


@dataclass
class Result:
    """结果定义"""
    task_id: int
    status: str  # "ok" or "error"
    data: Any
    error_msg: Optional[str] = None


class LRUCache:
    """LRU 缓存，用于限制 Client 数量"""

    def __init__(self, max_size: int = 20):
        self.max_size = max_size
        self._cache: OrderedDict = OrderedDict()

    def get(self, key: str):
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, key: str, value: Any) -> Optional[str]:
        """添加值，返回被驱逐的 key（如果有）"""
        evicted = None
        if key in self._cache:
            self._cache.move_to_end(key)
            self._cache[key] = value
        else:
            if len(self._cache) >= self.max_size:
                evicted, _ = self._cache.popitem(last=False)
            self._cache[key] = value
        return evicted

    def clear(self):
        self._cache.clear()

    def __len__(self):
        return len(self._cache)


class JuiceFSWorker:
    """工作进程实现"""

    # 支持的操作列表
    OPERATIONS = {
        "read", "write", "exists", "listdir", "mkdir", "makedirs",
        "remove", "rmdir", "rename", "stat", "truncate", "chmod",
        "getxattr", "setxattr", "listxattr", "removexattr",
    }

    def __init__(self,
                 task_queue: Queue,
                 result_queue: Queue,
                 worker_id: int,
                 max_tasks: int = 500,
                 max_clients: int = 20,
                 client_factory: Optional[Callable] = None):
        self.task_queue = task_queue
        self.result_queue = result_queue
        self.worker_id = worker_id
        self.max_tasks = max_tasks
        self.max_clients = max_clients
        self.client_factory = client_factory

    def run(self):
        """工作进程主循环"""
        # 延迟导入，避免 fork 问题
        from juicefs import Client

        # Client 缓存
        clients = LRUCache(max_size=self.max_clients)
        task_count = 0

        logger.info(f"Worker {self.worker_id} started, max_tasks={self.max_tasks}")

        while True:
            try:
                # 带超时的获取，允许空闲退出
                task_data = self.task_queue.get(timeout=60)
            except Empty:
                logger.info(f"Worker {self.worker_id} idle timeout, exiting")
                break

            if task_data is None:
                logger.info(f"Worker {self.worker_id} received shutdown signal")
                break

            task = Task(*task_data)
            result = self._handle_task(task, clients, Client)
            self.result_queue.put(result)

            task_count += 1

            # 达到任务上限，退出让主进程重启
            if task_count >= self.max_tasks:
                logger.info(f"Worker {self.worker_id} reached max_tasks ({self.max_tasks}), restarting")
                break

        # 清理资源
        clients.clear()
        logger.info(f"Worker {self.worker_id} stopped")

    def _handle_task(self, task: Task, clients: LRUCache, ClientClass) -> Result:
        """处理单个任务"""
        try:
            # 获取或创建 Client
            client = clients.get(task.meta_url)
            if client is None:
                client = ClientClass("volume", meta=task.meta_url)
                evicted = clients.put(task.meta_url, client)
                if evicted:
                    logger.debug(f"Worker {self.worker_id} evicted client for {evicted}")

            # 执行操作
            data = self._execute_operation(client, task.operation, task.args)

            return Result(
                task_id=task.task_id,
                status="ok",
                data=data
            )

        except Exception as e:
            logger.error(f"Worker {self.worker_id} error: {e}\n{traceback.format_exc()}")
            return Result(
                task_id=task.task_id,
                status="error",
                data=None,
                error_msg=str(e)
            )

    def _execute_operation(self, client, operation: str, args: tuple) -> Any:
        """执行文件系统操作"""
        if operation == "read":
            path, = args
            with client.open(path, "rb") as f:
                return f.read()

        elif operation == "write":
            path, data = args
            with client.open(path, "wb") as f:
                f.write(data)
            return len(data)

        elif operation == "exists":
            path, = args
            return client.exists(path)

        elif operation == "listdir":
            path, detail = args if len(args) > 1 else (args[0], False)
            return client.listdir(path, detail=detail)

        elif operation == "mkdir":
            path, mode = args if len(args) > 1 else (args[0], 0o777)
            client.mkdir(path, mode)
            return True

        elif operation == "makedirs":
            path, mode, exist_ok = args if len(args) > 2 else (args[0], 0o777, False)
            client.makedirs(path, mode, exist_ok)
            return True

        elif operation == "remove":
            path, = args
            client.remove(path)
            return True

        elif operation == "rmdir":
            path, = args
            client.rmdir(path)
            return True

        elif operation == "rename":
            old, new = args
            client.rename(old, new)
            return True

        elif operation == "stat":
            path, = args
            return client.stat(path)

        elif operation == "truncate":
            path, size = args
            client.truncate(path, size)
            return True

        elif operation == "chmod":
            path, mode = args
            client.chmod(path, mode)
            return True

        elif operation == "getxattr":
            path, name = args
            return client.getxattr(path, name)

        elif operation == "setxattr":
            path, name, value, flags = args if len(args) > 3 else (*args, 0)
            client.setxattr(path, name, value, flags)
            return True

        elif operation == "listxattr":
            path, = args
            return client.listxattr(path)

        elif operation == "removexattr":
            path, name = args
            client.removexattr(path, name)
            return True

        else:
            raise ValueError(f"Unknown operation: {operation}")


class JuiceFSWorkerPool:
    """JuiceFS 工作进程池"""

    def __init__(self,
                 num_workers: int = 4,
                 max_tasks_per_worker: int = 500,
                 max_clients_per_worker: int = 20):
        """
        初始化工作进程池

        Args:
            num_workers: 工作进程数量
            max_tasks_per_worker: 每个工作进程处理的最大任务数，超过后重启
            max_clients_per_worker: 每个工作进程缓存的最大 Client 数量
        """
        self.num_workers = num_workers
        self.max_tasks = max_tasks_per_worker
        self.max_clients = max_clients_per_worker

        self.task_queue: Optional[Queue] = None
        self.result_queue: Optional[Queue] = None
        self.workers: list = []
        self._running = False
        self._next_task_id = 0
        self._pending_results: Dict[int, Result] = {}

    def start(self):
        """启动工作进程池"""
        if self._running:
            return

        self.task_queue = Queue()
        self.result_queue = Queue()
        self.workers = []

        for i in range(self.num_workers):
            self._start_worker(i)

        self._running = True
        logger.info(f"Worker pool started with {self.num_workers} workers")

    def _start_worker(self, worker_id: int):
        """启动单个工作进程"""
        worker = JuiceFSWorker(
            task_queue=self.task_queue,
            result_queue=self.result_queue,
            worker_id=worker_id,
            max_tasks=self.max_tasks,
            max_clients=self.max_clients
        )
        p = mp.Process(target=worker.run, daemon=True)
        p.start()
        self.workers.append(p)
        logger.debug(f"Started worker {worker_id} (pid={p.pid})")

    def submit(self, meta_url: str, operation: str, *args) -> int:
        """
        提交任务到工作进程池

        Args:
            meta_url: JuiceFS 元数据地址
            operation: 操作名称
            *args: 操作参数

        Returns:
            task_id: 任务 ID，用于获取结果
        """
        if not self._running:
            raise RuntimeError("Worker pool not started")

        self._next_task_id += 1
        task_id = self._next_task_id

        self.task_queue.put((task_id, meta_url, operation, args))
        return task_id

    def get_result(self, task_id: int, timeout: float = 30.0) -> Any:
        """
        获取任务结果

        Args:
            task_id: 任务 ID
            timeout: 超时时间（秒）

        Returns:
            任务结果数据

        Raises:
            TimeoutError: 超时
            Exception: 任务执行错误
        """
        if not self._running:
            raise RuntimeError("Worker pool not started")

        deadline = time.time() + timeout

        while time.time() < deadline:
            # 先检查缓存的结果
            if task_id in self._pending_results:
                result = self._pending_results.pop(task_id)
                return self._process_result(result)

            # 从队列获取新结果
            try:
                result_data = self.result_queue.get(timeout=deadline - time.time())
                result = Result(*result_data) if isinstance(result_data, tuple) else result_data

                if result.task_id == task_id:
                    return self._process_result(result)
                else:
                    # 缓存其他任务的结果
                    self._pending_results[result.task_id] = result
            except Empty:
                continue

        raise TimeoutError(f"Task {task_id} timed out")

    def _process_result(self, result: Result) -> Any:
        """处理结果"""
        if result.status == "error":
            raise Exception(result.error_msg)
        return result.data

    def call(self, meta_url: str, operation: str, *args, timeout: float = 30.0) -> Any:
        """
        同步调用（提交并等待结果）

        Args:
            meta_url: JuiceFS 元数据地址
            operation: 操作名称
            *args: 操作参数
            timeout: 超时时间

        Returns:
            操作结果
        """
        task_id = self.submit(meta_url, operation, *args)
        return self.get_result(task_id, timeout)

    def restart_workers(self):
        """重启所有工作进程"""
        logger.info("Restarting all workers...")

        # 发送停止信号
        for _ in self.workers:
            self.task_queue.put(None)

        # 等待进程结束
        for p in self.workers:
            p.join(timeout=5)
            if p.is_alive():
                p.terminate()

        # 清理
        self.workers.clear()
        self._pending_results.clear()

        # 重新创建队列和启动进程
        self.task_queue = Queue()
        self.result_queue = Queue()

        for i in range(self.num_workers):
            self._start_worker(i)

        logger.info("Workers restarted")

    def check_and_restart(self):
        """检查工作进程状态，必要时重启"""
        dead_workers = [i for i, p in enumerate(self.workers) if not p.is_alive()]

        if dead_workers:
            logger.warning(f"Found {len(dead_workers)} dead workers, restarting...")
            for i in dead_workers:
                self.workers[i].join()
                self._start_worker(i)

    def stop(self):
        """停止工作进程池"""
        if not self._running:
            return

        logger.info("Stopping worker pool...")

        # 发送停止信号
        for _ in self.workers:
            try:
                self.task_queue.put(None, timeout=1)
            except:
                pass

        # 等待进程结束
        for p in self.workers:
            p.join(timeout=5)
            if p.is_alive():
                p.terminate()

        self.workers.clear()
        self._running = False
        logger.info("Worker pool stopped")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False


# 使用示例
if __name__ == "__main__":
    # 创建工作进程池
    pool = JuiceFSWorkerPool(
        num_workers=4,
        max_tasks_per_worker=100,  # 每 100 个任务重启一次
        max_clients_per_worker=10   # 每个 worker 最多缓存 10 个 Client
    )

    try:
        pool.start()

        # 示例：多用户操作
        users = [
            ("user1", "redis://localhost:6379/0"),
            ("user2", "redis://localhost:6379/1"),
            ("user3", "redis://localhost:6379/2"),
        ]

        for user, meta_url in users:
            # 写入文件
            task_id = pool.submit(
                meta_url, "write",
                f"/{user}/hello.txt",
                f"Hello from {user}".encode()
            )
            pool.get_result(task_id)
            print(f"[{user}] Written file")

            # 读取文件
            task_id = pool.submit(meta_url, "read", f"/{user}/hello.txt")
            content = pool.get_result(task_id)
            print(f"[{user}] Read: {content}")

            # 列出目录
            task_id = pool.submit(meta_url, "listdir", f"/{user}")
            files = pool.get_result(task_id)
            print(f"[{user}] Files: {files}")

        # 定期重启（可选，控制内存）
        # pool.restart_workers()

    finally:
        pool.stop()
```

### 6.4 配置建议

| 参数 | 建议值 | 说明 |
|------|--------|------|
| `num_workers` | CPU 核心数 | 并发处理能力 |
| `max_tasks_per_worker` | 500-1000 | 根据内存情况调整，越大越稳定但内存占用越高 |
| `max_clients_per_worker` | 10-20 | 活跃用户数较少时可增大 |

### 6.5 监控指标

```python
# 可添加的监控指标
- 当前活跃 Worker 数量
- 每个 Worker 处理的任务数
- 平均任务延迟
- 内存使用量
- Client 缓存命中率
```

---

## 7. 其他方案对比

| 方案 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| **任务队列模式** | 进程复用、内存可控、隔离性好 | 实现稍复杂 | 推荐：长期运行的多租户服务 |
| 修改 Go 源码 | 根本解决 | 需要维护 fork | 可以接受修改源码的场景 |
| 独立进程模式 | 完全隔离 | 资源开销大 | 低并发场景 |
| LRU 缓存模式 | 实现简单 | Go 侧不释放 | 用户数量有限的场景 |

---

## 8. 总结

### 问题根因

JuiceFS Python SDK 的 `jfs_term` 函数不释放底层 `FileSystem` 资源，这是设计决策（为了复用），但在多租户场景下会导致资源累积。

### 推荐方案

**任务队列模式**：
1. 工作进程复用，减少启动开销
2. LRU 缓存控制 Client 数量
3. 定期重启释放 Go 侧资源
4. 进程隔离保障稳定性

### 配置建议

```python
pool = JuiceFSWorkerPool(
    num_workers=4,              # 根据 CPU 核心数
    max_tasks_per_worker=500,   # 每 500 任务重启
    max_clients_per_worker=20   # 每进程最多 20 个 Client
)
```

### 注意事项

1. 定期调用 `pool.restart_workers()` 或让 worker 自动重启
2. 监控内存使用，调整 `max_tasks_per_worker`
3. 使用 `with` 语句确保资源释放
4. 生产环境建议添加健康检查和自动恢复机制

---

## 附录：关键代码位置

| 功能 | 文件路径 | 行号 |
|------|----------|------|
| Python Client | `sdk/python/juicefs/juicefs/juicefs.py` | 95-167 |
| Go 全局状态 | `sdk/java/libjfs/main.go` | 83-108 |
| getOrCreate | `sdk/java/libjfs/main.go` | 406-443 |
| jfs_term | `sdk/java/libjfs/main.go` | 908-951 |
| FileSystem 结构 | `pkg/fs/fs.go` | 136-162 |
| 元数据客户端 | `pkg/meta/redis.go` / `pkg/meta/sql.go` | 91-98 / 265-274 |