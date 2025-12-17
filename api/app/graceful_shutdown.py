import asyncio
from asyncio import Task
from contextvars import ContextVar, Token
import inspect
from threading import Thread
from contextlib import contextmanager, asynccontextmanager
from loguru import logger

TASK_GRACEFUL_SHUTDOWN_CONTEXT_VAR_NAME = "WAIT_FOR_GRACEFUL_SHUTDOWN"
TASK_GRACEFUL_SHUDOWN_TIMEOUT_CONTEXT_VAR_NAME = "WAIT_FOR_GRACEFUL_SHUTDOWN_TIMEOUT"

@contextmanager
def set_following_task_for_graceful_shutdown():
    """
    Set the context variable, which indicates that the task is waiting for graceful shutdown.
    """
    token = ContextVar(TASK_GRACEFUL_SHUTDOWN_CONTEXT_VAR_NAME).set(True)
    try:
        yield
    finally:
        ContextVar(TASK_GRACEFUL_SHUTDOWN_CONTEXT_VAR_NAME).reset(token)
        
@contextmanager
def set_following_task_for_graceful_shutdown_timeout(timeout: int):
    """
    Set the context variable, which indicates that the task is waiting for graceful shutdown.
    """
    token = ContextVar(TASK_GRACEFUL_SHUDOWN_TIMEOUT_CONTEXT_VAR_NAME).set(timeout)
    try:
        yield
    finally:
        ContextVar(TASK_GRACEFUL_SHUDOWN_TIMEOUT_CONTEXT_VAR_NAME).reset(token)

def is_graceful_shutdown_task(task: Task) -> bool:
    """
    Get the task context variable from the given task.
    """
    var = ContextVar(TASK_GRACEFUL_SHUTDOWN_CONTEXT_VAR_NAME, default=False)
    return bool(
        task.get_context().get(var, False)
        )
    
def get_graceful_shutdown_timeout(task: Task) -> int:
    """
    Get the task context variable from the given task.
    """
    var = ContextVar(TASK_GRACEFUL_SHUDOWN_TIMEOUT_CONTEXT_VAR_NAME, default=0)
    return int(
        task.get_context().get(var, 0)
        )
    
def loginfo_task_status(task: Task):
        logger.info("="*60)
        logger.info(f"任务名称: {task.get_name()}")
        logger.info(f"任务状态: {('已取消' if task.cancelled() else '已完成') if task.done() else '进行中'}")
        if task.done():
            return
        # 获取协程对象
        coro = task.get_coro()
        try:
            if hasattr(coro, 'cr_code'):
                code = coro.cr_code # type: ignore
                logger.info(f"   定义文件: {code.co_filename}")
                logger.info(f"   定义行号: {code.co_firstlineno}")
        except Exception as e:
            logger.info(f"   错误: {e}")
        try:
            stack = task.get_stack()
            if stack:
                logger.info(f"   栈深度: {len(stack)}")
                # 获取最顶层的栈帧（最近的调用）
                frame_info = inspect.getframeinfo(stack[-1])
                logger.info(f"   最近调用位置: {frame_info.filename}:{frame_info.lineno}")
                logger.info(f"   调用函数: {frame_info.function}")
                
                # 可选：显示调用代码
                import linecache
                code_line = linecache.getline(frame_info.filename, frame_info.lineno).strip()
                logger.info(f"   调用代码: {code_line}")
            else:
                logger.info("   无调用栈信息")
        except Exception as e:
            logger.info(f"   错误: {e}")
    
async def wait_background_task_for_graceful_shutdown() -> None:
    """
    Wait for graceful shutdown.
    """
    tasks = asyncio.all_tasks()
    tasks = [task for task in tasks if is_graceful_shutdown_task(task)]
    has_timeout_tasks = {
        task : get_graceful_shutdown_timeout(task)
        for task in tasks
        if get_graceful_shutdown_timeout(task) > 0
    }
    without_timeout_tasks = [
        task for task in tasks
        if get_graceful_shutdown_timeout(task) == 0
        ]
    
    async def wait_task_for_timeout(task: Task, timeout: int) -> None:
        await asyncio.sleep(timeout)
        task.cancel()
    
    # create background task to wait for timeout
    waiters = [
        asyncio.create_task(wait_task_for_timeout(task, timeout))
        for task, timeout in has_timeout_tasks.items()
        ]
    
    # wait for timeout
    while True:
        logger.info("="*60)
        logger.info("等待限时后台任务完成...")
        running_has_timeout_tasks = [
            task for task in has_timeout_tasks.keys()
            if not task.done()
            ]
        cancled_has_timeout_tasks = [
            task for task in has_timeout_tasks.keys()
            if task.done() and task.cancelled()
            ]
        completed_has_timeout_tasks = [
            task for task in has_timeout_tasks.keys()
            if task.done() and not task.cancelled()
            ]
        logger.info(f"正在运行的限时后台任务:【{len(running_has_timeout_tasks)}/{len(has_timeout_tasks)}】")
        logger.info(f"已取消的限时后台任务:【{len(cancled_has_timeout_tasks)}/{len(has_timeout_tasks)}】")
        logger.info(f"已完成的限时后台任务:【{len(completed_has_timeout_tasks)}/{len(has_timeout_tasks)}】")
        for task in running_has_timeout_tasks:
            loginfo_task_status(task)
        if not running_has_timeout_tasks:
            break
        await asyncio.sleep(10)
    
    # wait for infinite timeout
    while True:
        logger.info("="*60)
        logger.info("等待无限时后台任务完成...")
        running_without_timeout_tasks = [
            task for task in without_timeout_tasks
            if not task.done()
            ]
        cancled_without_timeout_tasks = [
            task for task in without_timeout_tasks
            if task.done() and task.cancelled()
            ]
        completed_without_timeout_tasks = [
            task for task in without_timeout_tasks
            if task.done() and not task.cancelled()
            ]
        logger.info(f"正在运行的无限时后台任务:【{len(running_without_timeout_tasks)}/{len(without_timeout_tasks)}】")
        logger.info(f"已取消的无限时后台任务:【{len(cancled_without_timeout_tasks)}/{len(without_timeout_tasks)}】")
        logger.info(f"已完成的无限时后台任务:【{len(completed_without_timeout_tasks)}/{len(without_timeout_tasks)}】")
        
        for task in running_without_timeout_tasks:
            loginfo_task_status(task)
        if not running_without_timeout_tasks:
            break
        await asyncio.sleep(10)
