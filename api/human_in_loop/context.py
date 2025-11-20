import pickle
from collections.abc import Iterable
from hashlib import sha256
from uuid import uuid4
import asyncio
from asyncio import Task
from api.redis import CLIENT

SEND_STREAM_KEY_PREFIX = "human_in_loop_send_stream"
RECV_STREAM_KEY_PREFIX = "human_in_loop_recv_stream"
STREAM_EXPIRE_TIME = 3600


class HILMessageStreamContext:
    def __init__(self, 
                 stream_identifier: str|Iterable[str],
                 expire_time = STREAM_EXPIRE_TIME):
        if isinstance(stream_identifier, str):
            self.stream_identifier = [stream_identifier]
        elif isinstance(stream_identifier, Iterable):
            self.stream_identifier = [str(i) for i in stream_identifier]
        else:
            raise ValueError("stream_identifier must be str or Iterable[str]")
        
        self.expire_time = expire_time
        self.deamon: Task | None = None

    async def TTL_deamon(self):
        while True:
            await asyncio.sleep(self.expire_time * 0.9)
            async with CLIENT.pipeline(transaction=True) as pipe:
                for id in self.stream_identifier:
                    pipe.expire(f"{SEND_STREAM_KEY_PREFIX}:{id}", self.expire_time)
                    pipe.expire(f"{RECV_STREAM_KEY_PREFIX}:{id}", self.expire_time)

    async def __aenter__(self) -> "HILMessageStreamContext":
        async with CLIENT.pipeline(transaction=True) as pipe:
            for id in self.stream_identifier:
                pipe.xgroup_create(f"{SEND_STREAM_KEY_PREFIX}:{id}", "dg", mkstream=True)
                pipe.xgroup_destroy(f"{SEND_STREAM_KEY_PREFIX}:{id}", "dg")
                pipe.expire(f"{SEND_STREAM_KEY_PREFIX}:{id}", self.expire_time)
                pipe.xgroup_create(f"{RECV_STREAM_KEY_PREFIX}:{id}", "dg", mkstream=True)
                pipe.xgroup_destroy(f"{RECV_STREAM_KEY_PREFIX}:{id}", "dg")
                pipe.expire(f"{RECV_STREAM_KEY_PREFIX}:{id}", self.expire_time)
            await pipe.execute()
        
        # start ttl deamon
        if self.deamon is not None:
            raise RuntimeError("HILMessageStreamContext is already in use")
        self.deamon = asyncio.create_task(self.TTL_deamon())

        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        async with CLIENT.pipeline(transaction=True) as pipe:
            for id in self.stream_identifier:
                pipe.delete(f"{SEND_STREAM_KEY_PREFIX}:{id}")
                pipe.delete(f"{RECV_STREAM_KEY_PREFIX}:{id}")
            await pipe.execute()
        
        if self.deamon is None:
            raise RuntimeError("HILMessageStreamContext is not in use")
        self.deamon.cancel()

