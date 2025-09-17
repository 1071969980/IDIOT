import pickle
from collections.abc import Iterable
from hashlib import sha256
from uuid import uuid4

from api.redis import CLIENT

SEND_STREAM_KEY_PREFIX = "human_in_loop_send_stream"
RECV_STREAM_KEY_PREFIX = "human_in_loop_recv_stream"
STREAM_EXPIRE_TIME = 3600 * 24


class HILMessageStreamContext:
    def __init__(self, stream_identifier: str|Iterable[str]):
        if isinstance(stream_identifier, str):
            self.stream_identifier = [stream_identifier]
        elif isinstance(stream_identifier, Iterable):
            self.stream_identifier = [str(i) for i in stream_identifier]
        else:
            raise ValueError("stream_identifier must be str or Iterable[str]")

    async def __aenter__(self) -> "HILMessageStreamContext":
        async with CLIENT.pipeline(transaction=True) as pipe:
            for id in self.stream_identifier:
                pipe.xgroup_create(f"{SEND_STREAM_KEY_PREFIX}:{id}", "dg", mkstream=True)
                pipe.xgroup_destroy(f"{SEND_STREAM_KEY_PREFIX}:{id}", "dg")
                pipe.expire(f"{SEND_STREAM_KEY_PREFIX}:{id}", STREAM_EXPIRE_TIME)
                pipe.xgroup_create(f"{RECV_STREAM_KEY_PREFIX}:{id}", "dg", mkstream=True)
                pipe.xgroup_destroy(f"{RECV_STREAM_KEY_PREFIX}:{id}", "dg")
                pipe.expire(f"{RECV_STREAM_KEY_PREFIX}:{id}", STREAM_EXPIRE_TIME)
            await pipe.execute()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        async with CLIENT.pipeline(transaction=True) as pipe:
            for id in self.stream_identifier:
                pipe.delete(f"{SEND_STREAM_KEY_PREFIX}:{id}")
                pipe.delete(f"{RECV_STREAM_KEY_PREFIX}:{id}")
            await pipe.execute()

