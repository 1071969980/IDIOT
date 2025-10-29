from asyncio import Task
from uuid import UUID
import asyncio

from .sql_stat.a2a_session_task.utils import (
    _A2ASessionTaskUpdate,
    task_exists,
    update_task_status,
    update_task_fields,
    get_tasks_by_status,
)

from .sql_stat.a2a_session.utils import (
    session_exists,
)

from .a2a_chat_task import a2a_chat_task

from typing import Any

class A2AChatTaskWorker:
    def __init__(self,
                 concurrency_limit: int = 10,
                 loop_interval: int = 5,
                 ):
        self.concurrency_limit = concurrency_limit
        self.task_pool: dict[UUID, Task] = {}
        self.stop_event = asyncio.Event()
        self.loop_interval = loop_interval

    def stop(self):
        self.stop_event.set()

    async def run(self):
        # 将来将这个worker移植到多进程环境时，创建任务的部分需要在多个进程中使用同步原语，以避免任务被重复处理。
        while True:
            await asyncio.sleep(self.loop_interval)
            if self.stop_event.is_set():
                break

            # clean up pool
            for task_id, task in self.task_pool.items():
                if task.done():
                    self.task_pool.pop(task_id)
                    if task.exception() is not None:
                        await update_task_status(task_id, "failed")
                        await update_task_fields(
                            _A2ASessionTaskUpdate(
                                task_id=task_id,
                                fields={
                                    "conclusion": f"Failed to execute task. Due to Exception: {str(task.exception())}"
                                }
                            )
                        )
                    elif task.cancelled():
                        await update_task_status(task_id, "cancelled")
                    else:
                        await update_task_status(task_id, "completed")


            # create tasks
            spare_pool_size = self.concurrency_limit - len(self.task_pool)
            if spare_pool_size <= 0:
                continue
            a2a_task_rows = await get_tasks_by_status("pending")
            if len(a2a_task_rows) > spare_pool_size:
                a2a_task_rows = a2a_task_rows[:spare_pool_size]

            for row in a2a_task_rows:
                await update_task_status(row.id, "processing")
                try:
                    task = asyncio.create_task(
                        a2a_chat_task(
                            session_id=row.session_id,
                            session_task_id=row.id,
                            proactive_side=row.proactive_side,
                            params=row.parmas,
                        )
                    )
                    self.task_pool[row.id] = task
                except Exception as e:
                    await update_task_status(row.id, "failed")
                    await update_task_fields(
                        _A2ASessionTaskUpdate(
                            task_id=row.id,
                            fields={
                                "conclusion": f"Failed to schedule task execution. Due to Exception: {str(e)}"
                            }
                        )
                    )


        


