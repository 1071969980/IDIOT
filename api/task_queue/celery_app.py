from celery import Celery
from .celery_task import AsyncAwareTask
from .utils import run_async_in_thread
import asyncio
import eventlet
from eventlet import monkey_patch, tpool
monkey_patch()

app = Celery('hello', broker='amqp://guest@localhost//')

async def sleep(seconds):
    await asyncio.sleep(seconds)

@app.task(base=AsyncAwareTask, bind=True)
def hello(self: AsyncAwareTask):
    loop = self._loop
    res = tpool.execute(run_async_in_thread, sleep(5), loop)