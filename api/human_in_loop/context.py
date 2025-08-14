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
            self.stream_identifier = [sha256(stream_identifier).hexdigest()]
        elif isinstance(stream_identifier, Iterable):
            self.stream_identifier = [sha256(i).hexdigest() for i in stream_identifier]
        else:
            raise ValueError("stream_identifier must be str or Iterable[str]")

    async def __aenter__(self) -> "HILMessageStreamContext":
        pickled_msg = pickle.dumps("init")
        msg_id = str(uuid4())
        async with CLIENT.pipeline(transaction=True) as pipe:
            for id in self.stream_identifier:
                pipe.xadd(f"{SEND_STREAM_KEY_PREFIX}:{id}",
                           {"msg": pickled_msg, "msg_id": msg_id})
                pipe.expire(f"{SEND_STREAM_KEY_PREFIX}:{id}", STREAM_EXPIRE_TIME)
                pipe.xadd(f"{RECV_STREAM_KEY_PREFIX}:{id}",
                           {"msg": pickled_msg, "msg_id": msg_id})
                pipe.expire(f"{RECV_STREAM_KEY_PREFIX}:{id}", STREAM_EXPIRE_TIME)
            await pipe.execute()
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        async with CLIENT.pipeline(transaction=True) as pipe:
            for id in self.stream_identifier:
                pipe.delete(f"{SEND_STREAM_KEY_PREFIX}:{id}")
            await pipe.execute()

