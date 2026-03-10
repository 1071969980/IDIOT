"""
Kubernetes stream 可中断执行示例

演示如何使用 _preload_content=False 实现可中断的 pod 命令执行，
同时能够获取执行结果。

支持:
- 同步线程模式
- 异步线程模式
- asyncio 模式

使用前需要:
    pip install kubernetes
"""

import asyncio
import threading
import time
from typing import Optional
from dataclasses import dataclass


@dataclass
class ExecResult:
    """执行结果"""
    stdout: str
    stderr: str
    returncode: Optional[int]
    interrupted: bool
    error: Optional[str] = None


class InterruptibleExec:
    """可中断的 Pod Exec 执行器"""

    def __init__(self):
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._result: Optional[ExecResult] = None
        self._client = None

    def execute(
        self,
        v1_api,
        pod_name: str,
        namespace: str,
        command: list[str],
        timeout: Optional[float] = None,
    ) -> ExecResult:
        """
        执行命令，支持外部中断。

        Args:
            v1_api: CoreV1Api 实例
            pod_name: Pod 名称
            namespace: 命名空间
            command: 要执行的命令
            timeout: 超时时间（秒），None 表示无超时

        Returns:
            ExecResult: 执行结果
        """
        from kubernetes.stream import stream

        self._stop_event.clear()
        self._result = None
        self._client = None

        def _run():
            try:
                # 关键：_preload_content=False 返回 WSClient 对象而不是阻塞
                self._client = stream(
                    v1_api.connect_get_namespaced_pod_exec,
                    name=pod_name,
                    namespace=namespace,
                    command=command,
                    stderr=True,
                    stdin=False,
                    stdout=True,
                    tty=False,
                    _preload_content=False,  # 不阻塞，返回 WSClient
                )

                # 使用短超时轮询，允许响应停止信号
                start_time = time.time()
                while self._client.is_open() and not self._stop_event.is_set():
                    # 检查超时
                    if timeout and (time.time() - start_time) > timeout:
                        self._result = ExecResult(
                            stdout=self._client.read_all(),
                            stderr="",
                            returncode=None,
                            interrupted=False,
                            error="Timeout",
                        )
                        self._client.close()
                        return

                    # 短超时 update，定期检查停止信号
                    self._client.update(timeout=0.5)

                # 获取结果
                if self._stop_event.is_set():
                    stdout = self._client.read_all()
                    self._client.close()
                    self._result = ExecResult(
                        stdout=stdout,
                        stderr="",
                        returncode=None,
                        interrupted=True,
                        error="Interrupted by stop_event",
                    )
                else:
                    # 正常结束
                    stdout = self._client.read_all()
                    returncode = self._client.returncode
                    self._result = ExecResult(
                        stdout=stdout,
                        stderr="",  # stderr 需要单独读取 channel
                        returncode=returncode,
                        interrupted=False,
                    )

            except Exception as e:
                self._result = ExecResult(
                    stdout="",
                    stderr="",
                    returncode=None,
                    interrupted=False,
                    error=str(e),
                )

        # 在线程中执行
        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

        # 等待完成
        self._thread.join()

        return self._result

    def interrupt(self):
        """中断执行"""
        self._stop_event.set()
        if self._client:
            self._client.close()

    def is_running(self) -> bool:
        """检查是否正在运行"""
        return self._thread is not None and self._thread.is_alive()


class AsyncInterruptibleExec:
    """
    异步版本的可中断执行器。

    适用于需要在执行期间做其他操作的场景。
    """

    def __init__(self):
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._result: Optional[ExecResult] = None
        self._client = None
        self._completed = threading.Event()

    def start(
        self,
        v1_api,
        pod_name: str,
        namespace: str,
        command: list[str],
        timeout: Optional[float] = None,
    ):
        """
        异步启动执行。

        Returns:
            self，支持链式调用
        """
        from kubernetes.stream import stream

        self._stop_event.clear()
        self._result = None
        self._client = None
        self._completed.clear()

        def _run():
            try:
                self._client = stream(
                    v1_api.connect_get_namespaced_pod_exec,
                    name=pod_name,
                    namespace=namespace,
                    command=command,
                    stderr=True,
                    stdin=False,
                    stdout=True,
                    tty=False,
                    _preload_content=False,
                )

                start_time = time.time()
                while self._client.is_open() and not self._stop_event.is_set():
                    if timeout and (time.time() - start_time) > timeout:
                        self._result = ExecResult(
                            stdout=self._client.read_all(),
                            stderr="",
                            returncode=None,
                            interrupted=False,
                            error="Timeout",
                        )
                        self._client.close()
                        self._completed.set()
                        return

                    self._client.update(timeout=0.5)

                if self._stop_event.is_set():
                    stdout = self._client.read_all()
                    self._client.close()
                    self._result = ExecResult(
                        stdout=stdout,
                        stderr="",
                        returncode=None,
                        interrupted=True,
                        error="Interrupted by stop_event",
                    )
                else:
                    stdout = self._client.read_all()
                    self._result = ExecResult(
                        stdout=stdout,
                        stderr="",
                        returncode=self._client.returncode,
                        interrupted=False,
                    )

            except Exception as e:
                self._result = ExecResult(
                    stdout="",
                    stderr="",
                    returncode=None,
                    interrupted=False,
                    error=str(e),
                )
            finally:
                self._completed.set()

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        return self

    def interrupt(self):
        """中断执行"""
        self._stop_event.set()
        if self._client:
            self._client.close()

    def wait(self, timeout: Optional[float] = None) -> Optional[ExecResult]:
        """等待执行完成，返回结果"""
        self._completed.wait(timeout=timeout)
        return self._result

    def is_running(self) -> bool:
        """检查是否正在运行"""
        return self._thread is not None and self._thread.is_alive()

    @property
    def result(self) -> Optional[ExecResult]:
        """获取结果（可能为 None 如果尚未完成）"""
        return self._result


# ============================================================================
# Mock 示例（无需真实 Kubernetes 集群）
# ============================================================================

class MockWSClient:
    """模拟 WSClient 用于演示"""

    def __init__(self, output: str, duration: float = 2.0):
        self._output = output
        self._duration = duration
        self._start_time = time.time()
        self._connected = True
        self._data = ""
        self._returncode = 0

    def is_open(self) -> bool:
        elapsed = time.time() - self._start_time
        if elapsed >= self._duration:
            self._connected = False
        return self._connected

    def update(self, timeout=0):
        """模拟更新，每次调用产出一些数据"""
        time.sleep(min(timeout, 0.1))
        elapsed = time.time() - self._start_time
        # 模拟逐步输出
        if elapsed < self._duration:
            chunk = f"[{elapsed:.1f}s] Working...\n"
            self._data += chunk

    def read_all(self) -> str:
        return self._data + self._output

    def read_channel(self, channel, timeout=0):
        return ""

    @property
    def returncode(self) -> int:
        return self._returncode

    def close(self):
        self._connected = False


def mock_stream(func, **kwargs):
    """模拟 stream 函数"""
    _preload_content = kwargs.get("_preload_content", True)

    # 模拟一个耗时 3 秒的命令
    client = MockWSClient(output="Command completed!\n", duration=3.0)

    if _preload_content:
        client.run_forever()
        return client.read_all()
    return client


def demo_sync_interruptible():
    """演示同步可中断执行"""
    print("\n" + "=" * 60)
    print("Demo 1: 同步执行（正常完成）")
    print("=" * 60)

    executor = InterruptibleExec()

    # 模拟正常执行
    result = executor.execute(
        v1_api=None,  # mock 不需要
        pod_name="test-pod",
        namespace="default",
        command=["sleep", "1"],
        timeout=10,
    )

    print(f"Stdout: {result.stdout}")
    print(f"Returncode: {result.returncode}")
    print(f"Interrupted: {result.interrupted}")


def demo_async_interruptible():
    """演示异步可中断执行"""
    print("\n" + "=" * 60)
    print("Demo 2: 异步执行 + 中断")
    print("=" * 60)

    # 使用 mock 演示
    import kubernetes.stream.ws_client as ws_client
    original_websocket_call = ws_client.websocket_call

    # 替换为 mock
    def mock_websocket_call(configuration, _method, url, **kwargs):
        class MockWSClientWithStop:
            def __init__(self):
                self._connected = True
                self._data = ""
                self._returncode = 0
                self._start = time.time()

            def is_open(self):
                # 模拟 5 秒执行时间
                if time.time() - self._start > 5:
                    self._connected = False
                return self._connected

            def update(self, timeout=0):
                elapsed = time.time() - self._start
                if elapsed < 5:
                    self._data += f"[{elapsed:.1f}s] Processing...\n"
                time.sleep(min(timeout, 0.1))

            def read_all(self):
                return self._data

            @property
            def returncode(self):
                return self._returncode

            def close(self):
                self._connected = False

        return MockWSClientWithStop()

    ws_client.websocket_call = mock_websocket_call

    try:
        executor = AsyncInterruptibleExec()

        print("启动长时间命令...")
        executor.start(
            v1_api=object(),  # mock
            pod_name="test-pod",
            namespace="default",
            command=["sleep", "100"],
        )

        # 模拟 2 秒后中断
        def interrupt_after(seconds):
            time.sleep(seconds)
            print(f"\n>>> {seconds}秒后触发中断 <<<")
            executor.interrupt()

        interrupt_thread = threading.Thread(target=interrupt_after, args=(2,))
        interrupt_thread.start()

        # 等待结果
        result = executor.wait()
        print(f"\n结果:")
        print(f"  Stdout: {result.stdout}")
        print(f"  Interrupted: {result.interrupted}")
        print(f"  Error: {result.error}")

    finally:
        ws_client.websocket_call = original_websocket_call


def demo_manual_control():
    """
    演示手动控制模式 - 最灵活的方式
    """
    print("\n" + "=" * 60)
    print("Demo 3: 手动控制模式（最灵活）")
    print("=" * 60)

    stop_event = threading.Event()
    result_container = {"stdout": "", "interrupted": False}

    def run_command():
        # 模拟 WSClient
        class MockClient:
            def __init__(self):
                self._connected = True
                self._data = ""
                self._start = time.time()

            def is_open(self):
                return self._connected

            def update(self, timeout=0):
                elapsed = time.time() - self._start
                if elapsed > 10:
                    self._connected = False
                else:
                    self._data += f"[{elapsed:.1f}s] Data chunk\n"
                time.sleep(min(timeout, 0.1))

            def read_all(self):
                return self._data

            def close(self):
                self._connected = False

        client = MockClient()

        while client.is_open() and not stop_event.is_set():
            client.update(timeout=0.5)

        result_container["stdout"] = client.read_all()
        result_container["interrupted"] = stop_event.is_set()
        client.close()

    # 启动线程
    thread = threading.Thread(target=run_command)
    thread.start()

    # 主线程做其他事情
    print("主线程可以并行做其他事情...")
    for i in range(3):
        if not thread.is_alive():
            break
        print(f"  主线程工作中... {i+1}")
        time.sleep(0.8)

    # 需要时中断
    print("\n>>> 触发中断 <<<")
    stop_event.set()
    thread.join(timeout=2)

    print(f"\n结果:")
    print(f"  Stdout: {result_container['stdout']}")
    print(f"  Interrupted: {result_container['interrupted']}")


# ============================================================================
# asyncio 版本（推荐用于异步应用）
# ============================================================================

class AsyncIOInterruptibleExec:
    """
    asyncio 版本的可中断执行器。

    适用于 FastAPI、asyncio 应用。
    注意：kubernetes.stream 是同步的，需要在 executor 中运行。
    """

    def __init__(self):
        self._stop_event = threading.Event()
        self._result: Optional[ExecResult] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def execute(
        self,
        v1_api,
        pod_name: str,
        namespace: str,
        command: list[str],
        timeout: Optional[float] = None,
    ) -> ExecResult:
        """
        异步执行命令，支持外部中断。

        Args:
            v1_api: CoreV1Api 实例
            pod_name: Pod 名称
            namespace: 命名空间
            command: 要执行的命令
            timeout: 超时时间（秒）

        Returns:
            ExecResult: 执行结果
        """
        self._stop_event.clear()
        self._result = None
        self._loop = asyncio.get_running_loop()

        def _sync_execute():
            from kubernetes.stream import stream

            try:
                client = stream(
                    v1_api.connect_get_namespaced_pod_exec,
                    name=pod_name,
                    namespace=namespace,
                    command=command,
                    stderr=True,
                    stdin=False,
                    stdout=True,
                    tty=False,
                    _preload_content=False,
                )

                start_time = time.time()
                while client.is_open() and not self._stop_event.is_set():
                    if timeout and (time.time() - start_time) > timeout:
                        stdout = client.read_all()
                        client.close()
                        self._result = ExecResult(
                            stdout=stdout,
                            stderr="",
                            returncode=None,
                            interrupted=False,
                            error="Timeout",
                        )
                        return

                    client.update(timeout=0.5)

                stdout = client.read_all()
                if self._stop_event.is_set():
                    client.close()
                    self._result = ExecResult(
                        stdout=stdout,
                        stderr="",
                        returncode=None,
                        interrupted=True,
                        error="Interrupted by stop_event",
                    )
                else:
                    self._result = ExecResult(
                        stdout=stdout,
                        stderr="",
                        returncode=client.returncode,
                        interrupted=False,
                    )

            except Exception as e:
                self._result = ExecResult(
                    stdout="",
                    stderr="",
                    returncode=None,
                    interrupted=False,
                    error=str(e),
                )

        # 在线程池中运行同步代码
        await self._loop.run_in_executor(None, _sync_execute)
        return self._result

    def interrupt(self):
        """中断执行"""
        self._stop_event.set()

    @property
    def result(self) -> Optional[ExecResult]:
        return self._result


class AsyncIOInterruptibleExecAdvanced:
    """
    高级 asyncio 版本 - 支持实时输出回调。

    适用于需要实时显示命令输出的场景。
    """

    def __init__(self):
        self._stop_event = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._output_queue: asyncio.Queue = asyncio.Queue()

    async def execute_with_callback(
        self,
        v1_api,
        pod_name: str,
        namespace: str,
        command: list[str],
        on_stdout: callable,  # async def on_stdout(data: str)
        on_stderr: callable = None,
        timeout: Optional[float] = None,
    ) -> ExecResult:
        """
        执行命令并实时回调输出。

        Args:
            v1_api: CoreV1Api 实例
            pod_name: Pod 名称
            namespace: 命名空间
            command: 要执行的命令
            on_stdout: 异步回调函数 async def (data: str)
            on_stderr: 异步回调函数 async def (data: str)
            timeout: 超时时间（秒）
        """
        from kubernetes.stream import stream

        self._stop_event.clear()
        self._loop = asyncio.get_running_loop()
        stdout_buffer = []
        stderr_buffer = []
        returncode = None
        error = None
        interrupted = False

        client = stream(
            v1_api.connect_get_namespaced_pod_exec,
            name=pod_name,
            namespace=namespace,
            command=command,
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False,
            _preload_content=False,
        )

        start_time = time.time()

        try:
            while client.is_open() and not self._stop_event.is_set():
                # 超时检查
                if timeout and (time.time() - start_time) > timeout:
                    error = "Timeout"
                    break

                # 短超时更新
                client.update(timeout=0.2)

                # 读取并回调 stdout
                stdout_data = client.read_channel(1, timeout=0)  # STDOUT_CHANNEL = 1
                if stdout_data:
                    stdout_buffer.append(stdout_data)
                    if on_stdout:
                        await on_stdout(stdout_data)

                # 读取并回调 stderr
                stderr_data = client.read_channel(2, timeout=0)  # STDERR_CHANNEL = 2
                if stderr_data:
                    stderr_buffer.append(stderr_data)
                    if on_stderr:
                        await on_stderr(stderr_data)

            if self._stop_event.is_set():
                interrupted = True
                error = "Interrupted by stop_event"

            returncode = client.returncode

        except Exception as e:
            error = str(e)
        finally:
            client.close()

        return ExecResult(
            stdout="".join(stdout_buffer),
            stderr="".join(stderr_buffer),
            returncode=returncode,
            interrupted=interrupted,
            error=error,
        )

    def interrupt(self):
        """中断执行"""
        self._stop_event.set()


# ============================================================================
# asyncio Demo
# ============================================================================

async def demo_asyncio_basic():
    """演示 asyncio 基本用法"""
    print("\n" + "=" * 60)
    print("Demo 4: asyncio 基本用法")
    print("=" * 60)

    # Mock 版本演示
    executor = AsyncIOInterruptibleExec()

    # 模拟执行（实际使用时需要真实 k8s 配置）
    print("在真实环境中，这里会执行 k8s 命令...")
    print("executor = AsyncIOInterruptibleExec()")
    print("result = await executor.execute(v1, 'pod-name', 'default', ['ls'])")


async def demo_asyncio_with_interrupt():
    """演示 asyncio + 中断"""
    print("\n" + "=" * 60)
    print("Demo 5: asyncio + 外部中断")
    print("=" * 60)

    executor = AsyncIOInterruptibleExec()

    async def interrupt_after(seconds: float):
        """模拟外部中断源（如用户取消、API 请求等）"""
        await asyncio.sleep(seconds)
        print(f"\n>>> {seconds}秒后触发中断 <<<")
        executor.interrupt()

    # 模拟场景：启动命令，2秒后中断
    # interrupt_task = asyncio.create_task(interrupt_after(2))
    # result = await executor.execute(v1, 'pod', 'ns', ['sleep', '100'])
    # interrupt_task.cancel()

    print("完整示例代码:")
    print("""
executor = AsyncIOInterruptibleExec()

# 在另一个任务中中断
async def cancel_after():
    await asyncio.sleep(2)
    executor.interrupt()

asyncio.create_task(cancel_after())

# 执行命令
result = await executor.execute(
    v1_api=v1,
    pod_name="my-pod",
    namespace="default",
    command=["sleep", "100"],
)
    """)


async def demo_asyncio_realtime_output():
    """演示实时输出回调"""
    print("\n" + "=" * 60)
    print("Demo 6: asyncio 实时输出回调")
    print("=" * 60)

    print("适用于需要实时显示命令输出的场景:")
    print("""
executor = AsyncIOInterruptibleExecAdvanced()

async def print_output(data: str):
    print(f"[输出] {data}", end="")

result = await executor.execute_with_callback(
    v1_api=v1,
    pod_name="my-pod",
    namespace="default",
    command=["/bin/sh", "-c", "for i in 1 2 3; do echo step $i; sleep 1; done"],
    on_stdout=print_output,
)
    """)


async def demo_asyncio_fastapi():
    """演示 FastAPI 集成"""
    print("\n" + "=" * 60)
    print("Demo 7: FastAPI 集成示例")
    print("=" * 60)

    print("""
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

app = FastAPI()

# 存储活跃的执行器，支持外部取消
active_executors: dict[str, AsyncIOInterruptibleExec] = {}

@app.post("/exec/{pod_name}")
async def exec_command(pod_name: str, command: list[str]):
    executor = AsyncIOInterruptibleExec()
    active_executors[pod_name] = executor

    try:
        result = await asyncio.wait_for(
            executor.execute(v1, pod_name, "default", command),
            timeout=60,
        )
        return {"stdout": result.stdout, "returncode": result.returncode}
    finally:
        active_executors.pop(pod_name, None)

@app.delete("/exec/{pod_name}")
async def cancel_exec(pod_name: str):
    if pod_name in active_executors:
        active_executors[pod_name].interrupt()
        return {"cancelled": True}
    raise HTTPException(404, "Executor not found")

# SSE 实时输出
@app.get("/exec/{pod_name}/stream")
async def exec_stream(pod_name: str, command: str):
    async def generate():
        executor = AsyncIOInterruptibleExecAdvanced()

        async def send_output(data: str):
            yield f"data: {data}\\n\\n"

        result = await executor.execute_with_callback(
            v1, pod_name, "default", command.split(),
            on_stdout=lambda d: None,  # 由 generate 处理
        )
        yield f"data: DONE, returncode={result.returncode}\\n\\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
    """)


# ============================================================================
# 真实 Kubernetes 使用示例
# ============================================================================

def example_real_kubernetes():
    """
    真实 Kubernetes 集群使用示例。

    需要:
    - 安装 kubernetes 包
    - 配置好 kubeconfig 或 in-cluster config
    """
    from kubernetes import config
    from kubernetes.client import CoreV1Api

    # 加载配置
    config.load_kube_config()  # 或 config.load_incluster_config()
    v1 = CoreV1Api()

    # 方式1: 同步执行
    executor = InterruptibleExec()
    result = executor.execute(
        v1_api=v1,
        pod_name="my-pod",
        namespace="default",
        command=["/bin/sh", "-c", "echo hello && sleep 5 && echo done"],
        timeout=10,
    )
    print(f"结果: {result}")

    # 方式2: 异步执行 + 中断
    async_executor = AsyncInterruptibleExec()
    async_executor.start(
        v1_api=v1,
        pod_name="my-pod",
        namespace="default",
        command=["/bin/sh", "-c", "while true; do echo running; sleep 1; done"],
    )

    # 做其他事情...
    time.sleep(3)

    # 中断
    async_executor.interrupt()
    result = async_executor.wait()
    print(f"中断后结果: {result}")


if __name__ == "__main__":
    print("Kubernetes Stream 可中断执行示例")
    print("=" * 60)

    # Demo 1: 手动控制模式（最灵活，推荐）
    demo_manual_control()

    # asyncio demos
    print("\n")
    asyncio.run(demo_asyncio_basic())
    asyncio.run(demo_asyncio_with_interrupt())
    asyncio.run(demo_asyncio_realtime_output())
    asyncio.run(demo_asyncio_fastapi())

    # 真实 Kubernetes 使用（取消注释运行）
    # example_real_kubernetes()