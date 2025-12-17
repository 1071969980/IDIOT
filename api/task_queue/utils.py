import asyncio
from typing import Callable, Coroutine

def run_async_in_thread(coro: Coroutine,
                        asyncio_loop: asyncio.AbstractEventLoop):
    """
    在线程中安全运行asyncio协程
    这个函数将在tpool的线程中执行
    """
    if not asyncio_loop or not asyncio_loop.is_running():
        raise RuntimeError("Asyncio loop not initialized")
    
    # 将协程提交到asyncio事件循环
    future = asyncio.run_coroutine_threadsafe(coro, asyncio_loop)
    
    # 等待结果（会阻塞当前线程，但不会阻塞Eventlet hub）
    return future.result()