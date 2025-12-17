import asyncio
import time
from celery import Task, current_task
import asyncio
import threading

class AsyncTaskStorege:
    """每个Worker持有一个的异步任务管理器"""
    
    def __init__(self, loop: asyncio.AbstractEventLoop):
        pass
    
    def can_accept_task(self) -> bool:
        return True
    
class AsyncAwareTask(Task):
    """支持异步队列的Celery任务基类"""
    
    _async_manager = None
    _loop = None
    
    def __init__(self, *args, **kwargs):
        threading.Thread(
            target=self._start_async_loop,
            daemon=True
        ).start()
        
        start_time = time.time()
        while self._loop is None and time.time() - start_time < 5:
            time.sleep(0.1)
        raise RuntimeError("Async loop not ready")
        
    def _start_async_loop(self):
        """启动异步事件循环（在独立线程中）"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop